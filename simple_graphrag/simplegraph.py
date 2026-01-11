"""
SimpleGraph - 核心知识图谱管理系统

面向对象的知识图谱管理类，支持：
- 异步任务队列处理
- 任务隔离（副本system）
- LLM智能合并
- 任务并发控制
- 进度追踪和回调
"""

import asyncio
import copy
import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime

from src.models.entity import (
    System,
    Entity,
    ClassDefinition,
    PropertyDefinition,
    ClassInstance,
)
from src.models.graph import Graph
from src.models.task import Task, generate_task_id
from src.models.delta import (
    GraphDelta,
    ClassDelta,
    EntityDelta,
    RelationshipDelta,
    PropertyDelta,
)
from src.models.relationship import Relationship
from src.llm.client import LLMClient
from src.updaters.system_updater import SystemUpdater
from src.extractors.extractor import GraphExtractor
from src.combiners.smart_merger import SmartMerger
from src.combiners.combiner import Combiner
from src.search.search_engine import SearchEngine
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SimpleGraph:
    """
    SimpleGraph - 知识图谱管理核心类

    功能：
    - 提交任务（submit_task）
    - 取消任务（cancel_task）
    - 查询任务状态（get_task_status）
    - 保存和可视化（save, visualize）
    - 统计信息（get_statistics）
    - 进度追踪（set_progress_callback, get_task_progress）

    任务处理流程（两阶段架构）：
    ┌─────────────────────────────────────────────────────────────┐
    │ 阶段1: 提取阶段（可并行）                                     │
    │ - 多个 workers 并行处理任务                                  │
    │ - System 更新（使用任务副本）                                │
    │ - 实体和关系提取                                             │
    │ - 生成 GraphDelta                                           │
    └─────────────────────────────────────────────────────────────┘
                            ↓ 进入合并队列
    ┌─────────────────────────────────────────────────────────────┐
    │ 阶段2: 合并阶段（串行执行）                                   │
    │ - 单个 merge worker 串行处理                                 │
    │ - LLM 智能合并（去重、对齐、冲突解决）                        │
    │ - 应用到主 system/graph                                      │
    │ - 确保数据一致性和合并质量                                   │
    └─────────────────────────────────────────────────────────────┘

    优势：
    1. 提取阶段可以充分并行，提高吞吐量
    2. 合并阶段串行执行，保证数据一致性
    3. 详细的进度通知，包括等待合并状态
    4. 每个阶段的进度和结果可通过回调获取
    """

    def __init__(
        self,
        config_path: Path,
        max_concurrent_tasks: int = 3,
        enable_smart_merge: bool = True,
        progress_callback: Optional[Callable[[str, str, dict], None]] = None,
    ):
        """
        初始化SimpleGraph

        Args:
            config_path: 配置文件路径（config.yaml）
            max_concurrent_tasks: 最大并发任务数
            enable_smart_merge: 是否启用LLM智能合并
            progress_callback: 进度回调函数，签名为 (task_id, step, progress_data) -> None
        """
        logger.info("=" * 60)
        logger.info("初始化 SimpleGraph")
        logger.info("=" * 60)

        self.config_path = config_path
        self.config = self._load_config()
        self.config_dir = config_path.parent
        self.max_concurrent_tasks = max_concurrent_tasks
        self.enable_smart_merge = enable_smart_merge

        # 初始化 LLM 客户端
        logger.info("初始化 LLM 客户端...")
        model_config = self.config["models"]["default_chat_model"]
        api_key = self._get_api_key(model_config)
        verbose = model_config.get("verbose", False)

        self.llm_client = LLMClient(
            provider="ark",
            model="deepseek-v3-2-251201",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            verbose=verbose,
        )
        logger.info(f"LLM 客户端初始化完成 (verbose={verbose})")

        # 加载预定义 System 和创建 Graph
        logger.info("加载预定义 System...")
        self.system = System.from_config_file(self.config_path, use_base_system=True)
        logger.info(f"System 加载完成: {len(self.system.get_all_classes())} 个类")

        self.graph = Graph(system=self.system, include_predefined_entities=True)
        logger.info(
            f"Graph 创建完成: {self.graph.get_entity_count()} 个实体（含预定义）"
        )

        # 任务管理
        self.tasks: Dict[str, Task] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()  # 任务队列（用于提取阶段）
        self.merge_queue: asyncio.Queue = asyncio.Queue()  # 合并队列（串行执行）

        # 初始化智能合并器
        smart_merge_prompt_path = self.config_dir / "prompts" / "smart_merge.txt"
        self.merger = SmartMerger(
            llm_client=self.llm_client,
            prompt_path=smart_merge_prompt_path,
            enable_smart_merge=enable_smart_merge,
        )
        logger.info(f"智能合并器初始化完成 (enable_smart_merge={enable_smart_merge})")

        # 初始化简单合并器（用于应用增量）
        self.combiner = Combiner(self.graph, strict_validation=False)

        # 初始化搜索引擎并关联到Graph
        self.search_engine = self.graph._search_engine
        logger.info("搜索引擎初始化完成")

        # 并发控制
        self._worker_tasks: List[asyncio.Task] = []  # 提取任务的workers
        self._merge_worker_task: Optional[asyncio.Task] = None  # 合并worker（只有1个）
        self._running: bool = False

        # 进度回调
        self._progress_callback = progress_callback

        logger.info("SimpleGraph 初始化完成")
        logger.info("=" * 60)

    def _load_config(self) -> dict:
        """加载配置文件"""
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return self._replace_env_vars(config)

    def _replace_env_vars(self, obj):
        """递归替换环境变量"""
        if isinstance(obj, dict):
            return {k: self._replace_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            return os.environ.get(env_var, obj)
        return obj

    def _get_api_key(self, model_config: dict) -> str:
        """获取 API Key"""
        api_key = model_config.get("api_key")
        if api_key and api_key.startswith("${") and api_key.endswith("}"):
            api_key = os.environ.get(api_key[2:-1])
        elif not api_key:
            api_key = os.environ.get("MIMO_API_KEY")
        return api_key

    async def start(self):
        """启动任务处理器"""
        if self._running:
            logger.warning("任务处理器已经在运行")
            return

        logger.info(f"启动 {self.max_concurrent_tasks} 个提取workers和1个合并worker...")
        self._running = True

        # 启动提取workers（可以并行）
        for i in range(self.max_concurrent_tasks):
            worker = asyncio.create_task(self._worker(worker_id=i))
            self._worker_tasks.append(worker)

        # 启动合并worker（只有1个，串行处理）
        self._merge_worker_task = asyncio.create_task(self._merge_worker())

        logger.info("任务处理器启动完成")

    async def stop(self):
        """停止任务处理器"""
        if not self._running:
            return

        logger.info("停止任务处理器...")
        self._running = False

        # 取消所有提取workers
        for worker in self._worker_tasks:
            worker.cancel()

        # 取消合并worker
        if self._merge_worker_task:
            self._merge_worker_task.cancel()

        # 等待所有worker结束
        all_workers = self._worker_tasks + (
            [self._merge_worker_task] if self._merge_worker_task else []
        )
        await asyncio.gather(*all_workers, return_exceptions=True)

        self._worker_tasks.clear()
        self._merge_worker_task = None
        logger.info("任务处理器已停止")

    async def submit_task(self, input_text: str) -> str:
        """
        提交任务

        Args:
            input_text: 输入的自然语言文本

        Returns:
            任务ID
        """
        task_id = generate_task_id()

        # 创建system副本（任务隔离）
        system_snapshot = self._create_system_snapshot()

        # 创建任务
        task = Task(
            task_id=task_id,
            input_text=input_text,
            status="pending",
            system_snapshot=system_snapshot,
        )

        self.tasks[task_id] = task
        await self.task_queue.put(task)

        logger.info(f"任务已提交: {task_id[:8]}...")
        logger.debug(f"任务内容: {input_text[:100]}...")

        return task_id

    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"任务不存在: {task_id}")
            return False

        if task.is_finished():
            logger.warning(f"任务已结束，无法取消: {task_id}")
            return False

        task.cancel()
        logger.info(f"任务已取消: {task_id[:8]}...")
        return True

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态字典，如果任务不存在返回None
        """
        task = self.tasks.get(task_id)
        if not task:
            return None

        return task.to_dict(include_snapshot=False)

    def get_all_tasks(self) -> List[dict]:
        """
        获取所有任务列表

        Returns:
            任务列表
        """
        return [task.to_dict(include_snapshot=False) for task in self.tasks.values()]

    def set_progress_callback(self, callback: Callable[[str, str, dict], None]):
        """
        设置进度回调函数

        Args:
            callback: 回调函数，签名为 (task_id, step, progress_data) -> None
        """
        self._progress_callback = callback

    def get_task_progress(self, task_id: str) -> Optional[dict]:
        """
        获取任务的当前进度

        Args:
            task_id: 任务ID

        Returns:
            进度信息字典
        """
        task = self.tasks.get(task_id)
        if not task:
            return None
        return task.progress

    def get_task_stage_results(self, task_id: str) -> Optional[dict]:
        """
        获取任务的所有阶段结果

        Args:
            task_id: 任务ID

        Returns:
            阶段结果字典
        """
        task = self.tasks.get(task_id)
        if not task:
            return None
        return task.get_all_stage_results()

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        task_statuses = {}
        for status in ["pending", "running", "completed", "failed", "cancelled"]:
            task_statuses[status] = sum(
                1 for task in self.tasks.values() if task.status == status
            )

        return {
            "system": {
                "classes": len(self.system.get_all_classes()),
                "predefined_entities": len(self.system.predefined_entities),
            },
            "graph": {
                "entities": self.graph.get_entity_count(),
                "relationships": self.graph.get_relationship_count(),
            },
            "tasks": {
                "total": len(self.tasks),
                "by_status": task_statuses,
            },
        }

    def save(self, path: Path):
        """
        保存graph到文件

        Args:
            path: 保存路径
        """
        logger.info(f"保存 Graph 到: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.graph.save(path)
        logger.info(f"Graph 保存成功: {path}")

    @classmethod
    def load(cls, config_path: Path, graph_path: Path, **kwargs) -> "SimpleGraph":
        """
        从文件加载graph并创建SimpleGraph实例

        Args:
            config_path: 配置文件路径
            graph_path: graph文件路径
            **kwargs: 其他初始化参数（max_concurrent_tasks, enable_smart_merge等）

        Returns:
            加载的SimpleGraph实例
        """
        logger.info(f"从文件加载 Graph: {graph_path}")

        if not graph_path.exists():
            raise FileNotFoundError(f"Graph文件不存在: {graph_path}")

        # 创建SimpleGraph实例（不包含预定义实体，因为会从文件加载）
        instance = cls(config_path=config_path, **kwargs)

        # 加载graph（会覆盖默认创建的空graph）
        instance.graph = Graph.load(graph_path)

        # 同步system（从加载的graph中获取）
        instance.system = instance.graph.system

        # 重新初始化 combiner，让它引用新加载的 graph 实例
        # 这是关键修复：确保 combiner 操作的是新加载的 graph，而不是初始化时的空 graph
        from src.combiners.combiner import Combiner

        instance.combiner = Combiner(instance.graph, strict_validation=False)

        logger.info(
            f"Graph 加载成功: {instance.graph.get_entity_count()} 个实体, "
            f"{instance.graph.get_relationship_count()} 个关系"
        )

        return instance

    def visualize(self, output_path: Path, render_class_master_nodes: bool = True):
        """
        生成可视化

        Args:
            output_path: 输出路径
            render_class_master_nodes: 是否渲染类主节点
        """
        logger.info(f"生成可视化: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        from graph_visualizer import GraphVisualizer

        visualizer = GraphVisualizer(title="Knowledge Graph")
        visualizer.from_simple_graphrag(
            self.graph, render_class_master_nodes=render_class_master_nodes
        )

    def _create_system_snapshot(self) -> System:
        """深拷贝当前system作为副本"""
        return copy.deepcopy(self.system)

    def _notify_progress(self, task_id: str, step: str, data: dict):
        """
        通知进度回调

        Args:
            task_id: 任务ID
            step: 当前步骤
            data: 进度数据
        """
        if self._progress_callback:
            try:
                self._progress_callback(task_id, step, data)
            except Exception as e:
                logger.error(f"进度回调失败: {e}", exc_info=True)

    def _check_cancelled(self, task: Task):
        """检查任务是否被取消"""
        if task.is_cancelled():
            raise asyncio.CancelledError(f"任务 {task.task_id} 被取消")

    async def _run_task(self, task: Task) -> GraphDelta:
        """
        执行单个任务，返回增量更新包

        Args:
            task: 任务对象（包含system_snapshot和input_text）

        Returns:
            GraphDelta增量更新包

        Raises:
            asyncio.CancelledError: 如果任务被取消
        """
        logger.info(f"开始执行任务: {task.task_id}")
        logger.debug(f"输入文本: {task.input_text[:100]}...")

        # 使用任务的system副本
        system = task.system_snapshot
        if system is None:
            raise ValueError("任务的system_snapshot不能为None")

        # 初始化增量数据
        class_deltas: List[ClassDelta] = []
        entity_deltas: List[EntityDelta] = []
        relationship_deltas: List[RelationshipDelta] = []

        try:
            # 检查取消
            self._check_cancelled(task)

            # Step 1: 增量扩展 System
            step_msg = "正在分析文本并更新System类定义..."
            task.update_progress("system_update", step_msg, 10)
            self._notify_progress(
                task.task_id, "system_update", {"message": step_msg, "percentage": 10}
            )

            logger.info(f"[任务 {task.task_id[:8]}] 🔧 开始System更新阶段")
            logger.info(
                f"[任务 {task.task_id[:8]}] 输入文本: {task.input_text[:100]}..."
            )

            # 记录输入数据
            system_update_input = {
                "input_text": task.input_text,
                "existing_classes": system.get_all_classes(),
                "classes_count": len(system.get_all_classes()),
            }

            system, class_changes = await self._step_update_system(
                system, task.input_text
            )

            # 详细日志输出
            if class_changes.get("needed"):
                logger.info(f"[任务 {task.task_id[:8]}] ✅ System更新完成:")
                for class_name in class_changes.get("added_classes", []):
                    class_def = system.get_class_definition(class_name)
                    if class_def:
                        logger.info(f"  ✨ 新增类: {class_name}")
                        logger.info(f"     描述: {class_def.description}")
                        props = [p.name for p in class_def.properties]
                        logger.info(
                            f"     属性: {', '.join(props) if props else '(无)'}"
                        )

                for class_name in class_changes.get("enhanced_classes", []):
                    class_def = system.get_class_definition(class_name)
                    if class_def:
                        logger.info(f"  🔧 增强类: {class_name}")
                        logger.info(f"     描述: {class_def.description}")
                        props = [p.name for p in class_def.properties]
                        logger.info(
                            f"     属性: {', '.join(props) if props else '(无)'}"
                        )
            else:
                logger.info(
                    f"[任务 {task.task_id[:8]}] ✓ System无需更新，现有类定义已足够"
                )

            # 构建详细的类信息
            added_classes_detail = []
            for class_name in class_changes.get("added_classes", []):
                class_def = system.get_class_definition(class_name)
                if class_def:
                    added_classes_detail.append(
                        {
                            "name": class_name,
                            "description": class_def.description,
                            "properties": [p.name for p in class_def.properties],
                        }
                    )

            enhanced_classes_detail = []
            for class_name in class_changes.get("enhanced_classes", []):
                class_def = system.get_class_definition(class_name)
                if class_def:
                    enhanced_classes_detail.append(
                        {
                            "name": class_name,
                            "description": class_def.description,
                            "properties": [p.name for p in class_def.properties],
                        }
                    )

            # 记录输出数据
            system_update_output = {
                "needed": class_changes.get("needed", False),
                "added_classes": class_changes.get("added_classes", []),
                "enhanced_classes": class_changes.get("enhanced_classes", []),
                "added_classes_detail": added_classes_detail,
                "enhanced_classes_detail": enhanced_classes_detail,
                "total_classes_in_system": len(system.get_all_classes()),
                "llm_response_summary": class_changes.get("details", ""),
            }

            # 保存阶段结果（包含详细的输入输出和LLM响应）
            task.update_progress(
                "system_update",
                "System更新完成",
                30,
                result={
                    "needed": class_changes.get("needed", False),
                    "added_classes": class_changes.get("added_classes", []),
                    "enhanced_classes": class_changes.get("enhanced_classes", []),
                    "added_classes_detail": added_classes_detail,
                    "enhanced_classes_detail": enhanced_classes_detail,
                    "total_classes_in_system": len(system.get_all_classes()),
                    "details": class_changes.get("details", ""),
                },
                input_data=system_update_input,
                output_data=system_update_output,
                llm_response=class_changes.get("llm_raw_response"),
            )
            self._notify_progress(
                task.task_id,
                "system_update",
                {
                    "message": "System更新完成",
                    "percentage": 30,
                    "result": task.get_stage_result("system_update"),
                },
            )

            # 记录类的变更
            for class_name in class_changes.get("added_classes", []):
                class_def = system.get_class_definition(class_name)
                if class_def:
                    class_deltas.append(
                        ClassDelta(
                            name=class_def.name,
                            description=class_def.description,
                            properties=[
                                PropertyDelta(
                                    name=prop.name,
                                    description=prop.description,
                                    required=prop.required,
                                    value_required=prop.value_required,
                                    operation="add",
                                )
                                for prop in class_def.properties
                            ],
                            operation="add",
                        )
                    )

            for class_name in class_changes.get("enhanced_classes", []):
                class_def = system.get_class_definition(class_name)
                if class_def:
                    class_deltas.append(
                        ClassDelta(
                            name=class_def.name,
                            description=class_def.description,
                            properties=[
                                PropertyDelta(
                                    name=prop.name,
                                    description=prop.description,
                                    required=prop.required,
                                    value_required=prop.value_required,
                                    operation="update",
                                )
                                for prop in class_def.properties
                            ],
                            operation="update",
                        )
                    )

            # 检查取消
            self._check_cancelled(task)

            # Step 2: 提取实体和关系
            step_msg = "正在从文本中提取实体和关系..."
            task.update_progress("extraction", step_msg, 50)
            self._notify_progress(
                task.task_id, "extraction", {"message": step_msg, "percentage": 50}
            )

            logger.info(f"[任务 {task.task_id[:8]}] 🔍 开始实体和关系提取阶段")

            # 记录提取阶段的输入
            extraction_input = {
                "input_text": task.input_text,
                "available_classes": system.get_all_classes(),
                "system_classes_count": len(system.get_all_classes()),
            }

            entities, relationships, extraction_llm_response = await self._step_extract(
                system, task.input_text
            )

            # 详细日志输出
            logger.info(f"[任务 {task.task_id[:8]}] ✅ 提取完成:")
            logger.info(f"  📦 提取到 {len(entities)} 个实体:")
            for entity in entities:
                classes_str = ", ".join([c.class_name for c in entity.classes])
                logger.info(f"     • {entity.name} [{classes_str}]")
                logger.info(f"       描述: {entity.description}")
                # 显示属性
                for class_instance in entity.classes:
                    if class_instance.properties:
                        props_items = []
                        for k, v in class_instance.properties.items():
                            if v.value:
                                props_items.append(f"{k}={v.value}")
                        if props_items:
                            logger.info(f"       属性: {', '.join(props_items)}")

            logger.info(f"  🔗 提取到 {len(relationships)} 个关系:")
            for rel in relationships:
                count_str = f" (x{rel.count})" if rel.count > 1 else ""
                logger.info(f"     • {rel.source} → {rel.target}{count_str}")
                logger.info(f"       {rel.description}")

            # 构建详细的实体信息
            entities_detail = []
            for entity in entities:
                entity_info = {
                    "name": entity.name,
                    "description": entity.description,
                    "classes": [c.class_name for c in entity.classes],
                    "properties": {},
                }
                # 收集所有类的属性
                for class_instance in entity.classes:
                    if class_instance.properties:
                        entity_info["properties"][class_instance.class_name] = {
                            k: v.value for k, v in class_instance.properties.items()
                        }
                entities_detail.append(entity_info)

            # 构建详细的关系信息
            relationships_detail = []
            for rel in relationships:
                relationships_detail.append(
                    {
                        "source": rel.source,
                        "target": rel.target,
                        "description": rel.description,
                        "count": rel.count,
                    }
                )

            # 记录提取阶段的输出
            extraction_output = {
                "entities_count": len(entities),
                "relationships_count": len(relationships),
                "entities": entities_detail,
                "relationships": relationships_detail,
                "entity_names": [e.name for e in entities],
                "entity_classes": list(
                    set([c.class_name for e in entities for c in e.classes])
                ),
            }

            # 保存阶段结果（包含详细的输入输出和LLM响应）
            task.update_progress(
                "extraction",
                "提取完成",
                80,
                result={
                    "entities_count": len(entities),
                    "relationships_count": len(relationships),
                    "entities": entities_detail,
                    "relationships": relationships_detail,
                    "entity_names": [e.name for e in entities],
                    "entity_classes": list(
                        set([c.class_name for e in entities for c in e.classes])
                    ),
                },
                input_data=extraction_input,
                output_data=extraction_output,
                llm_response=extraction_llm_response,
            )
            self._notify_progress(
                task.task_id,
                "extraction",
                {
                    "message": "提取完成",
                    "percentage": 80,
                    "result": task.get_stage_result("extraction"),
                },
            )

            # 转换为增量格式
            for entity in entities:
                # 提取实体的属性值
                properties_dict = {}
                for class_instance in entity.classes:
                    class_props = {}
                    for prop_name, prop_value in class_instance.properties.items():
                        class_props[prop_name] = prop_value.value or ""
                    if class_props:
                        properties_dict[class_instance.class_name] = class_props

                entity_deltas.append(
                    EntityDelta(
                        name=entity.name,
                        description=entity.description,
                        classes=[c.class_name for c in entity.classes],
                        properties=properties_dict,
                        operation="add",
                    )
                )

            for relationship in relationships:
                relationship_deltas.append(
                    RelationshipDelta(
                        source=relationship.source,
                        target=relationship.target,
                        description=relationship.description,
                        count=relationship.count,
                        refer=relationship.refer,  # 传递 refer 字段
                        operation="add",
                    )
                )

            # 检查取消
            self._check_cancelled(task)

            # 构建GraphDelta
            delta = GraphDelta(
                task_id=task.task_id,
                classes=class_deltas,
                entities=entity_deltas,
                relationships=relationship_deltas,
                metadata={
                    "input_text": task.input_text[:200],
                    "entities_count": len(entity_deltas),
                    "relationships_count": len(relationship_deltas),
                    "classes_added": len(
                        [c for c in class_deltas if c.operation == "add"]
                    ),
                },
            )

            logger.info(f"任务执行完成: {delta.get_summary()}")
            return delta

        except asyncio.CancelledError:
            logger.info(f"任务被取消: {task.task_id}")
            raise
        except Exception as e:
            logger.error(f"任务执行失败: {e}", exc_info=True)
            raise

    async def _worker(self, worker_id: int):
        """
        任务工作线程（异步）

        Args:
            worker_id: Worker ID
        """
        logger.info(f"Worker {worker_id} 启动")

        while self._running:
            try:
                # 从队列获取任务（带超时）
                try:
                    task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                logger.info(f"Worker {worker_id} 开始处理任务: {task.task_id[:8]}...")

                # 标记任务开始
                task.start()
                self._notify_progress(
                    task.task_id, "started", {"message": "任务已开始", "percentage": 0}
                )

                try:
                    # 执行任务（提取阶段，可并行）
                    delta = await self._run_task(task)

                    # 标记任务完成（提取阶段）
                    task.complete(delta)
                    self._notify_progress(
                        task.task_id,
                        "extraction_completed",
                        {
                            "message": "提取阶段完成，等待合并",
                            "percentage": 90,
                            "summary": delta.get_summary(),
                        },
                    )

                    # 将任务放入合并队列（串行处理）
                    await self.merge_queue.put(task)

                    logger.info(
                        f"Worker {worker_id} 提取完成，任务进入合并队列: {task.task_id[:8]}..."
                    )

                except asyncio.CancelledError:
                    task.cancel()
                    self._notify_progress(
                        task.task_id, "cancelled", {"message": "任务已取消"}
                    )
                    logger.info(f"Worker {worker_id} 任务被取消: {task.task_id[:8]}...")

                except Exception as e:
                    task.fail(str(e))
                    self._notify_progress(
                        task.task_id, "failed", {"message": f"任务失败: {e}"}
                    )
                    logger.error(
                        f"Worker {worker_id} 任务失败: {task.task_id[:8]}..., 错误: {e}",
                        exc_info=True,
                    )

                finally:
                    self.task_queue.task_done()

            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} 被取消")
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} 发生未预期错误: {e}", exc_info=True)

        logger.info(f"Worker {worker_id} 停止")

    async def _merge_worker(self):
        """
        合并worker（串行处理合并任务）

        这个worker从merge_queue中获取已完成提取的任务，
        逐个进行智能合并，确保合并过程串行执行，保证数据一致性。
        """
        logger.info("Merge Worker 启动（串行处理）")

        while self._running:
            try:
                # 从合并队列获取任务（带超时）
                try:
                    task = await asyncio.wait_for(self.merge_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                logger.info(f"Merge Worker 开始合并任务: {task.task_id[:8]}...")

                # 通知进入合并阶段
                self._notify_progress(
                    task.task_id,
                    "merging",
                    {
                        "message": "开始智能合并到主图谱",
                        "percentage": 95,
                    },
                )

                try:
                    # 执行合并（串行，无需加锁）
                    await self._auto_merge(task)

                    # 合并成功，标记任务最终完成
                    self._notify_progress(
                        task.task_id,
                        "completed",
                        {
                            "message": "任务已完成并合并",
                            "percentage": 100,
                        },
                    )

                    logger.info(f"Merge Worker 任务合并完成: {task.task_id[:8]}...")

                except Exception as e:
                    # 合并失败
                    task.fail(str(e))
                    self._notify_progress(
                        task.task_id,
                        "merge_failed",
                        {
                            "message": f"合并失败: {e}",
                            "percentage": 95,
                        },
                    )
                    logger.error(
                        f"Merge Worker 任务合并失败: {task.task_id[:8]}..., 错误: {e}",
                        exc_info=True,
                    )

                finally:
                    self.merge_queue.task_done()

            except asyncio.CancelledError:
                logger.info("Merge Worker 被取消")
                break
            except Exception as e:
                logger.error(f"Merge Worker 发生未预期错误: {e}", exc_info=True)

        logger.info("Merge Worker 停止")

    async def _auto_merge(self, task: Task):
        """
        自动合并（在merge_worker中串行调用，无需加锁）

        Args:
            task: 已完成的任务
        """
        if not task.result_delta or task.result_delta.is_empty():
            logger.info(f"任务 {task.task_id[:8]} 增量为空，跳过合并")
            return

        logger.info(f"开始智能合并任务结果: {task.task_id[:8]}...")

        # 记录合并阶段的输入数据（详细）
        delta_dict = task.result_delta.to_dict()
        merge_input = {
            "delta_summary": task.result_delta.get_summary(),
            "enable_smart_merge": self.enable_smart_merge,
            "current_state": {
                "system_classes": len(self.system.get_all_classes()),
                "graph_entities": self.graph.get_entity_count(),
                "graph_relationships": self.graph.get_relationship_count(),
            },
            "delta_to_merge": {
                "classes": delta_dict.get("classes", []),
                "entities": delta_dict.get("entities", []),
                "relationships": delta_dict.get("relationships", []),
            },
            "statistics": {
                "classes_to_merge": len(delta_dict.get("classes", [])),
                "entities_to_merge": len(delta_dict.get("entities", [])),
                "relationships_to_merge": len(delta_dict.get("relationships", [])),
            },
        }

        try:
            # 智能合并
            merge_result = await self.merger.merge_delta(
                self.system,
                self.graph,
                task.result_delta,
            )

            logger.info(f"智能合并完成: {merge_result.get_summary()}")

            # 应用优化后的增量到主system/graph
            stats = await self._apply_merge_result(merge_result.optimized_delta)

            logger.info(f"任务结果已合并到主图谱: {task.task_id[:8]}...")

            # 记录合并阶段的输出数据（详细）
            optimized_dict = merge_result.optimized_delta.to_dict()
            merge_output = {
                "merge_summary": merge_result.get_summary(),
                "merge_statistics": {
                    "duplicates_found": merge_result.duplicates_found,
                    "conflicts_resolved": merge_result.conflicts_resolved,
                    "names_aligned": merge_result.names_aligned,
                    "descriptions_optimized": merge_result.descriptions_optimized,
                },
                "merge_notes": merge_result.notes,
                "apply_statistics": {
                    "entities_added": stats.get("entities", {}).get("added", 0),
                    "entities_updated": stats.get("entities", {}).get("updated", 0),
                    "relationships_added": stats.get("relationships", {}).get(
                        "added", 0
                    ),
                    "relationships_updated": stats.get("relationships", {}).get(
                        "updated", 0
                    ),
                },
                "final_state": {
                    "system_classes": len(self.system.get_all_classes()),
                    "graph_entities": self.graph.get_entity_count(),
                    "graph_relationships": self.graph.get_relationship_count(),
                },
                "optimized_delta": {
                    "classes": optimized_dict.get("classes", []),
                    "entities": optimized_dict.get("entities", []),
                    "relationships": optimized_dict.get("relationships", []),
                },
            }

            # 保存合并阶段结果（包含LLM输入输出）
            task.update_progress(
                "merging",
                "合并完成",
                95,
                result={
                    "summary": merge_result.get_summary(),
                    "entities_added": stats.get("entities", {}).get("added", 0),
                    "entities_updated": stats.get("entities", {}).get("updated", 0),
                    "relationships_added": stats.get("relationships", {}).get(
                        "added", 0
                    ),
                    "relationships_updated": stats.get("relationships", {}).get(
                        "updated", 0
                    ),
                },
                input_data=merge_input,
                output_data=merge_output,
                llm_response=merge_result.llm_response,
            )

        except Exception as e:
            logger.error(f"合并失败: {e}", exc_info=True)
            raise

    async def _step_update_system(
        self, system: System, text: str
    ) -> tuple[System, Dict]:
        """
        步骤1: 增量扩展 System（异步）

        Returns:
            (更新后的System, 变更信息)
        """
        logger.debug("步骤1: 检查并增量扩展 System")

        # 初始化 SystemUpdater
        updater = SystemUpdater(self.llm_client)

        # 检查并更新
        system, changes = await self._check_and_update_async(updater, system, text)

        if changes["needed"]:
            logger.info(f"System 已扩展:")
            logger.info(f"  新增类: {changes['added_classes']}")
            logger.info(f"  增强类: {changes['enhanced_classes']}")
        else:
            logger.debug("System 无需扩展")

        return system, changes

    async def _check_and_update_async(
        self, updater: SystemUpdater, system: System, text: str
    ) -> tuple[System, Dict]:
        """异步版本的check_and_update"""
        logger.debug("检查 System 是否需要扩展（异步）")

        # 一次性完成检查和配置生成（返回3个值）
        need_update, incremental_config, llm_response = (
            await self._check_and_generate_async(updater, system, text)
        )

        if not need_update:
            logger.debug("现有 System 足够，无需扩展")
            return system, {
                "needed": False,
                "added_classes": [],
                "enhanced_classes": [],
                "details": "现有系统足够",
                "llm_raw_response": llm_response,
            }

        if not incremental_config or "classes" not in incremental_config:
            logger.warning("LLM 未返回有效的增量配置")
            return system, {
                "needed": True,
                "added_classes": [],
                "enhanced_classes": [],
                "details": "LLM 未返回有效配置",
            }

        logger.info(f"需要扩展 System，涉及 {len(incremental_config['classes'])} 个类")

        # 应用更新
        added, enhanced = updater._apply_update(system, incremental_config)
        logger.info(
            f"System 扩展完成: 新增 {len(added)} 个类, 增强 {len(enhanced)} 个类"
        )

        return system, {
            "needed": True,
            "added_classes": added,
            "enhanced_classes": enhanced,
            "details": f"新增 {len(added)} 个类, 增强 {len(enhanced)} 个类",
        }

    async def _check_and_generate_async(
        self, updater: SystemUpdater, system: System, text: str
    ) -> tuple[bool, Dict, str]:
        """异步版本的_check_and_generate，返回 (need_update, config, llm_response)"""
        system_yaml = yaml.dump(
            {
                "classes": {
                    name: system.get_class_definition(name).to_dict()
                    for name in system.get_all_classes()
                }
            },
            allow_unicode=True,
            default_flow_style=False,
        )

        logger.debug("调用 LLM 检查并生成配置（异步）...")
        response = await self.llm_client.extract_text_async(
            prompt_template=updater.prompt_template,
            temperature=0.3,
            system_yaml=system_yaml,
            text=text,
        )

        logger.debug(f"LLM 响应长度: {len(response)} 字符")

        # 解析响应
        if "SUFFICIENT" in response.upper():
            logger.debug("LLM 判断：系统足够")
            return False, {}, response

        # 尝试解析为 YAML 配置
        try:
            config = updater._parse_yaml_response(response)
            if config and "classes" in config and config["classes"]:
                logger.debug(f"解析到增量配置: {list(config['classes'].keys())}")
                return True, config, response
            else:
                logger.warning("LLM 响应不包含有效的类定义")
                return False, {}, response
        except Exception as e:
            logger.error(f"解析 LLM 响应失败: {e}")
            return False, {}, response

    async def _step_extract(
        self, system: System, text: str
    ) -> tuple[List[Entity], List, str]:
        """
        步骤2: 提取实体和关系（异步）

        Returns:
            (实体列表, 关系列表, LLM响应)
        """
        logger.debug("步骤2: 提取实体和关系")

        # 初始化 GraphExtractor
        extraction_config = self.config.get("extraction", {})
        prompts_config = self.config["prompts"]
        extract_prompt_path = self.config_dir / prompts_config["extract_graph"]

        # 准备基础实体信息
        base_entities = [
            {
                "name": e.name,
                "description": e.description,
                "classes": e.classes,
            }
            for e in system.predefined_entities
        ]

        extractor = GraphExtractor(
            llm_client=self.llm_client,
            prompt_template_path=extract_prompt_path,
            classes=system.get_all_classes(),
            system=system,
            tuple_delimiter=extraction_config.get("tuple_delimiter", "|"),
            record_delimiter=extraction_config.get("record_delimiter", "^"),
            completion_delimiter=extraction_config.get("completion_delimiter", "DONE"),
            language=extraction_config.get("language", "中文"),
            base_entities=base_entities,
            enable_check=extraction_config.get("enable_check", True),
        )

        # 异步提取
        entities, relationships, llm_response = await self._extract_async(
            extractor, text
        )

        logger.info(f"提取完成: {len(entities)} 个实体, {len(relationships)} 个关系")

        return entities, relationships, llm_response

    async def _extract_async(self, extractor: GraphExtractor, text: str):
        """异步版本的extract，返回 (entities, relationships, llm_response)"""
        logger.debug("开始异步三步提取：实体 -> 类属性 -> 关系")

        # 准备模板变量
        classes_str = ",".join(extractor.classes)
        classes_info = extractor._generate_classes_info()
        base_entities_info = extractor._format_base_entities()

        # 调用LLM提取（异步）
        logger.debug("调用LLM进行三步提取（异步）...")
        response = await self.llm_client.extract_text_async(
            prompt_template=extractor.prompt_template,
            input_text=text,
            entity_types=classes_str,
            tuple_delimiter=extractor.tuple_delimiter,
            record_delimiter=extractor.record_delimiter,
            completion_delimiter=extractor.completion_delimiter,
            language=extractor.language,
            classes_info=classes_info,
            base_entities_info=base_entities_info,
        )

        logger.debug(f"LLM响应长度: {len(response)} 字符")

        # 如果启用检查，进行二次优化（异步）
        if extractor.enable_check:
            logger.info("开始检查和优化提取结果（异步）...")
            checked_response = await self._check_extraction_async(
                extractor, text, response, classes_str
            )
            response = checked_response
            logger.info("检查优化完成")

        # 解析响应
        entities, relationships = extractor._parse_response(response)

        return entities, relationships, response

    async def _check_extraction_async(
        self,
        extractor: GraphExtractor,
        input_text: str,
        extraction_result: str,
        entity_types: str,
    ) -> str:
        """异步版本的_check_extraction"""
        logger.debug("调用检查LLM优化提取结果（异步）...")

        response = await self.llm_client.extract_text_async(
            prompt_template=extractor.check_template,
            temperature=0.3,
            input_text=input_text,
            extraction_result=extraction_result,
            entity_types=entity_types,
        )

        return response

    async def _apply_merge_result(self, optimized_delta: GraphDelta):
        """
        应用优化后的增量到主system/graph

        Args:
            optimized_delta: 优化后的增量更新包

        Returns:
            合并统计信息
        """
        logger.debug("应用增量更新到主system/graph...")

        # 应用类增量到system
        for class_delta in optimized_delta.classes:
            properties = [
                PropertyDefinition(
                    name=prop.name,
                    description=prop.description,
                    required=prop.required if prop.required is not None else False,
                    value_required=(
                        prop.value_required
                        if prop.value_required is not None
                        else False
                    ),
                )
                for prop in class_delta.properties
            ]

            class_def = ClassDefinition(
                name=class_delta.name,
                description=class_delta.description,
                properties=properties,
            )

            self.system.add_class_definition(class_def)

        # 应用实体和关系增量到graph
        # 转换增量为Entity和Relationship对象
        entities = []
        for entity_delta in optimized_delta.entities:
            entity = Entity(
                name=entity_delta.name,
                description=entity_delta.description or "",
            )

            # 添加类和属性
            for class_name in entity_delta.classes:
                class_instance = entity.add_class(class_name, system=self.system)

                # 设置属性值
                class_props = entity_delta.properties.get(class_name, {})
                for prop_name, prop_value in class_props.items():
                    try:
                        entity.set_property_value(
                            class_name, prop_name, value=prop_value, system=self.system
                        )
                    except Exception as e:
                        logger.warning(f"设置属性失败: {e}")

            entities.append(entity)

        relationships = []
        increment_count_stats = {"incremented": 0, "not_found": 0}

        for rel_delta in optimized_delta.relationships:
            if rel_delta.operation == "increment_count":
                # 处理increment_count操作：查找并增加现有关系的count
                increment_amount = rel_delta.increment_amount
                if increment_amount <= 0:
                    logger.warning(
                        f"increment_count操作的increment_amount无效: {increment_amount}, "
                        f"关系: {rel_delta.source} -> {rel_delta.target}"
                    )
                    continue

                # 查找匹配的现有关系（source、target、description、refer都相同）
                found = False
                for existing_rel in self.graph.get_relationships():
                    # 使用大小写不敏感比较
                    source_match = (
                        existing_rel.source.upper() == rel_delta.source.upper()
                    )
                    target_match = (
                        existing_rel.target.upper() == rel_delta.target.upper()
                    )
                    desc_match = existing_rel.description == rel_delta.description
                    # refer数组比较（顺序无关，大小写不敏感）
                    refer_set_existing = set([r.upper() for r in existing_rel.refer])
                    refer_set_delta = set([r.upper() for r in rel_delta.refer])
                    refer_match = refer_set_existing == refer_set_delta

                    if source_match and target_match and desc_match and refer_match:
                        # 找到匹配的关系，增加其count
                        old_count = existing_rel.count
                        existing_rel.count += increment_amount

                        # 追加语义时间到现有关系
                        if rel_delta.semantic_times:
                            existing_rel.semantic_times.extend(rel_delta.semantic_times)
                            logger.info(
                                f"increment_count: {rel_delta.source} -> {rel_delta.target}, "
                                f"count从 {old_count} 增加到 {existing_rel.count} (+{increment_amount}), "
                                f"追加 {len(rel_delta.semantic_times)} 个语义时间"
                            )
                        else:
                            logger.info(
                                f"increment_count: {rel_delta.source} -> {rel_delta.target}, "
                                f"count从 {old_count} 增加到 {existing_rel.count} (+{increment_amount})"
                            )

                        found = True
                        increment_count_stats["incremented"] += 1
                        break

                if not found:
                    logger.warning(
                        f"increment_count操作未找到匹配的现有关系: "
                        f"{rel_delta.source} -> {rel_delta.target} "
                        f"(description={rel_delta.description}, refer={rel_delta.refer}), "
                        f"将作为新关系添加"
                    )
                    # 未找到匹配关系，作为新关系添加
                    relationship = Relationship(
                        source=rel_delta.source,
                        target=rel_delta.target,
                        description=rel_delta.description,
                        count=increment_amount,  # 使用increment_amount作为初始count
                        refer=rel_delta.refer,
                        semantic_times=rel_delta.semantic_times,  # 传递 semantic_times 字段
                    )
                    relationships.append(relationship)
                    increment_count_stats["not_found"] += 1
            else:
                # 其他操作：正常添加关系
                relationship = Relationship(
                    source=rel_delta.source,
                    target=rel_delta.target,
                    description=rel_delta.description,
                    count=rel_delta.count,
                    refer=rel_delta.refer,  # 传递 refer 字段
                    semantic_times=rel_delta.semantic_times,  # 传递 semantic_times 字段
                )
                relationships.append(relationship)

        # 使用Combiner合并到graph
        stats = self.combiner.combine(entities, relationships)

        # 添加increment_count统计
        if (
            increment_count_stats["incremented"] > 0
            or increment_count_stats["not_found"] > 0
        ):
            logger.info(
                f"increment_count操作统计: 成功增加 {increment_count_stats['incremented']} 个, "
                f"未找到匹配 {increment_count_stats['not_found']} 个"
            )

        logger.info(
            f"应用增量完成: 实体 +{stats['entities']['added']}/~{stats['entities']['updated']}, "
            f"关系 +{stats['relationships']['added']}/~{stats['relationships']['updated']}"
        )

        return stats

    # ==================== 搜索功能 ====================

    def search_keyword(
        self, keyword: str, fuzzy: bool = True, limit: Optional[int] = None
    ):
        """
        关键词搜索

        Args:
            keyword: 搜索关键词
            fuzzy: 是否模糊搜索
            limit: 结果数量限制

        Returns:
            搜索结果列表
        """
        return self.search_engine.search_keyword(keyword, fuzzy, limit)

    def get_node_detail(self, node_id: str):
        """
        获取节点详情

        Args:
            node_id: 节点ID（可以是实体名、类节点ID等）

        Returns:
            节点详情对象
        """
        return self.search_engine.get_node_detail(node_id)

    def get_entity_node_group(self, entity_name: str):
        """
        获取实体节点组（实体+所有类节点+一层关系）

        Args:
            entity_name: 实体名称

        Returns:
            实体节点组对象
        """
        return self.search_engine.get_entity_node_group(entity_name)

    def get_class_node_group(self, class_name: str):
        """
        获取类节点组（所有该类的实体类节点）

        Args:
            class_name: 类名称

        Returns:
            类节点组对象
        """
        return self.search_engine.get_class_node_group(class_name)
