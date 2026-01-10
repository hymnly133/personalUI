import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
import json

# 将 simple_graphrag 添加到 python 路径
sys.path.append(str(Path(__file__).parent.parent / "simple_graphrag"))

from simplegraph import SimpleGraph
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GraphService:
    def __init__(self):
        self.sg: Optional[SimpleGraph] = None
        self.config_path = (
            Path(__file__).parent.parent / "simple_graphrag" / "config" / "config.yaml"
        )
        self.data_dir = Path(__file__).parent / "data"  # 数据目录
        self.data_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在
        self.task_progress: Dict[str, Any] = {}
        self.task_events = asyncio.Queue()
        self.auto_save_enabled = True  # 默认启用自动保存

    async def initialize(self, auto_load: bool = True):
        """
        初始化 SimpleGraph

        Args:
            auto_load: 是否自动加载默认数据库（如果存在）
        """
        if self.sg:
            return

        # 检查是否存在默认数据库文件
        default_db_path = self.get_default_database_path()
        should_load = auto_load and default_db_path.exists()

        if should_load:
            logger.info(f"检测到默认数据库文件，正在加载: {default_db_path}")
            try:
                # 从文件加载
                self.sg = SimpleGraph.load(
                    config_path=self.config_path,
                    graph_path=default_db_path,
                    max_concurrent_tasks=3,
                    enable_smart_merge=True,
                    progress_callback=self._on_progress,
                )
                await self.sg.start()
                logger.info(
                    f"已从默认数据库加载: {self.sg.graph.get_entity_count()} 个实体"
                )
            except Exception as e:
                logger.error(f"加载默认数据库失败: {e}，将创建新数据库", exc_info=True)
                should_load = False

        if not should_load:
            # 创建新的空数据库
            logger.info("创建新的空数据库...")
            self.sg = SimpleGraph(
                config_path=self.config_path,
                max_concurrent_tasks=3,
                enable_smart_merge=True,
                progress_callback=self._on_progress,
            )
            await self.sg.start()
            logger.info("新数据库创建完成")

        logger.info("SimpleGraph service initialized and started.")

    def _on_progress(self, task_id: str, step: str, data: dict):
        """进度回调"""
        # 计算进度百分比
        step_percentages = {
            "submitted": 5,
            "started": 10,
            "extracting_entities": 30,
            "extracting_relationships": 50,
            "merging": 70,
            "building_graph": 90,
            "completed": 100,
            "failed": 0,
        }

        percentage = data.get("percentage") or step_percentages.get(step, 0)

        progress_info = {
            "event_type": "progress",
            "task_id": task_id,
            "step": step,
            "message": data.get("message", f"Processing: {step}"),
            "percentage": percentage,
            "result": data.get("result"),
            "timestamp": data.get("timestamp"),
            "status": "running" if step not in ["completed", "failed"] else step,
        }
        self.task_progress[task_id] = progress_info

        # 将进度放入队列，供 SSE 使用
        try:
            asyncio.create_task(self.task_events.put(progress_info))
        except Exception as e:
            logger.error(f"Failed to put progress event: {e}")

        # 任务完成后自动保存
        # 注意：这里需要确保合并操作已经完全完成后再保存
        #
        # 关键问题分析：
        # 1. _notify_progress 是在 _auto_merge 完成后立即调用的（同步调用）
        # 2. _on_progress 是同步回调，它使用 asyncio.create_task 创建异步任务
        # 3. asyncio.create_task 创建的异步任务会在当前事件循环的下一个迭代中执行
        # 4. 但是，_auto_merge 是异步的，它应该已经完成了
        #
        # 为了确保合并操作已经完全应用到图中，我们需要：
        # - 等待事件循环完成当前迭代（使用 asyncio.sleep(0)）
        # - 验证任务状态确实为 completed
        # - 然后再执行保存操作
        if step == "completed" and self.auto_save_enabled:
            try:

                async def delayed_save():
                    # 首先让事件循环完成当前迭代，确保所有待处理的合并操作都已完成
                    await asyncio.sleep(0)

                    # 再次让事件循环完成一个迭代，确保合并操作完全应用到图中
                    await asyncio.sleep(0.1)

                    # 验证任务确实已完成合并
                    if not self.sg:
                        logger.warning("SimpleGraph 未初始化，跳过自动保存")
                        return

                    task_status = self.sg.get_task_status(task_id)
                    if not task_status or task_status.get("status") != "completed":
                        logger.warning(
                            f"任务 {task_id[:8]} 状态不是 completed，跳过自动保存"
                        )
                        return

                    # 执行保存操作
                    await self._auto_save_after_task(task_id)

                # 使用 asyncio.ensure_future 确保任务被正确调度
                asyncio.ensure_future(delayed_save())
            except Exception as e:
                logger.error(f"Failed to schedule auto-save: {e}", exc_info=True)

    async def _auto_save_after_task(self, task_id: str):
        """任务完成后自动保存数据库"""
        try:
            logger.info(f"任务 {task_id[:8]} 完成，开始自动保存数据库...")

            # 在保存前验证合并是否真的完成
            if self.sg:
                # 获取保存前的统计信息
                stats_before = self.sg.get_statistics()
                logger.info(f"保存前统计: {stats_before}")

                # 获取任务的增量数据
                task_delta = self.get_task_delta(task_id)
                if task_delta and task_delta.get("has_delta"):
                    delta_stats = task_delta.get("stats", {})
                    logger.info(f"任务增量统计: {delta_stats}")

            result = await self.save_database()

            # 验证保存后的统计信息
            if self.sg:
                stats_after = self.sg.get_statistics()
                logger.info(f"保存后统计: {stats_after}")

            logger.info(f"自动保存成功: {result.get('message')}")

            # 发送保存成功事件
            save_event = {
                "event_type": "auto_save",
                "task_id": task_id,
                "message": "数据库已自动保存",
                "file_path": result.get("file_path"),
                "file_size": result.get("file_size"),
            }
            await self.task_events.put(save_event)

        except Exception as e:
            logger.error(f"自动保存失败: {e}", exc_info=True)
            # 发送保存失败事件
            error_event = {
                "event_type": "auto_save_error",
                "task_id": task_id,
                "message": f"数据库自动保存失败: {str(e)}",
            }
            try:
                await self.task_events.put(error_event)
            except Exception as put_error:
                logger.error(f"Failed to put error event: {put_error}")

    async def submit_task(self, input_text: str) -> str:
        """提交任务"""
        if not self.sg:
            await self.initialize()

        # 提交任务
        task_id = await self.sg.submit_task(input_text)

        # 发送任务提交事件
        submit_event = {
            "event_type": "task_submitted",
            "task_id": task_id,
            "message": "Task submitted successfully",
            "timestamp": None,
        }
        try:
            await self.task_events.put(submit_event)
        except Exception as e:
            logger.error(f"Failed to put submit event: {e}")

        return task_id

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        if not self.sg:
            return None
        return self.sg.get_task_status(task_id)

    def get_task_delta(self, task_id: str) -> Optional[dict]:
        """获取任务的增量数据"""
        if not self.sg:
            return None

        task = self.sg.tasks.get(task_id)
        if not task:
            return None

        # 如果任务还没有完成，返回空
        if task.status != "completed" or not task.result_delta:
            return {
                "task_id": task_id,
                "status": task.status,
                "has_delta": False,
                "delta": None,
            }

        # 返回增量数据
        delta_dict = task.result_delta.to_dict()

        # 计算统计信息
        stats = {
            "classes": len(delta_dict.get("classes", [])),
            "entities": len(delta_dict.get("entities", [])),
            "relationships": len(delta_dict.get("relationships", [])),
        }

        return {
            "task_id": task_id,
            "status": task.status,
            "has_delta": True,
            "delta": delta_dict,
            "stats": stats,
            "input_text": task.input_text,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": (
                task.completed_at.isoformat() if task.completed_at else None
            ),
        }

    def get_task_stage_details(self, task_id: str) -> Optional[dict]:
        """
        获取任务各阶段的详细数据（包括输入、输出、LLM响应）

        Args:
            task_id: 任务ID

        Returns:
            包含各阶段详细数据的字典
        """
        if not self.sg:
            return None

        task = self.sg.tasks.get(task_id)
        if not task:
            return None

        # 获取所有阶段结果
        stage_results = task.get_all_stage_results()

        # 格式化返回数据
        stages_data = {}
        for stage_name, stage_data in stage_results.items():
            stages_data[stage_name] = {
                "timestamp": stage_data.get("timestamp"),
                "result": stage_data.get("result"),  # 摘要结果
                "input": stage_data.get("input"),  # 输入数据
                "output": stage_data.get("output"),  # 输出数据
                "llm_response": stage_data.get("llm_response"),  # LLM原始响应
            }

        return {
            "task_id": task_id,
            "status": task.status,
            "input_text": task.input_text,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": (
                task.completed_at.isoformat() if task.completed_at else None
            ),
            "duration": task.get_duration(),
            "stages": stages_data,
        }

    def get_all_tasks(self) -> List[dict]:
        """获取所有任务"""
        if not self.sg:
            return []
        return self.sg.get_all_tasks()

    def get_graph_data(self) -> dict:
        """获取图数据，格式化为前端 D3.js 所需格式"""
        if not self.sg:
            return {"nodes": [], "links": []}

        graph = self.sg.graph
        nodes = []
        links = []

        # 类主节点
        for master in graph.get_class_master_nodes():
            nodes.append(
                {
                    "id": master.node_id,
                    "label": master.class_name,
                    "group": 0,
                    "size": 12,
                    "description": master.description
                    or f"类主节点: {master.class_name}",
                    "node_type": "class_master",
                    "classes": [master.class_name],
                }
            )

        # 实体节点和类节点
        for i, entity in enumerate(graph.get_entities()):
            entity_classes = [c.class_name for c in entity.classes]
            nodes.append(
                {
                    "id": entity.name,
                    "label": entity.name,
                    "group": i + 1,
                    "size": 15,
                    "description": entity.description or f"实体: {entity.name}",
                    "node_type": "entity",
                    "classes": entity_classes,
                    "properties": {
                        c.class_name: {k: v.value for k, v in c.properties.items()}
                        for c in entity.classes
                    },
                }
            )

            for class_name in entity_classes:
                class_node_id = f"{entity.name}:{class_name}"
                class_node = graph.get_class_node(entity.name, class_name)
                nodes.append(
                    {
                        "id": class_node_id,
                        "label": class_node_id,
                        "group": i + 1,
                        "size": 10,
                        "description": (
                            class_node.description
                            if class_node
                            else f"{entity.name} 的 {class_name} 类"
                        ),
                        "node_type": "class_node",
                        "classes": [class_name],
                    }
                )

                # 边：实体 -> 类节点
                links.append(
                    {
                        "source": entity.name,
                        "target": class_node_id,
                        "value": 1,
                        "description": f"实体: {entity.name} 拥有 {class_name} 类",
                        "edge_type": "has_class",
                    }
                )

                # 边：类节点 -> 类主节点
                links.append(
                    {
                        "source": class_node_id,
                        "target": class_name,
                        "value": 1,
                        "description": f"{class_node_id} 属于 {class_name} 类",
                        "edge_type": "instance_of_class",
                    }
                )

        # 关系边
        for rel in graph.get_relationships():
            links.append(
                {
                    "source": rel.source,
                    "target": rel.target,
                    "value": min(rel.count * 0.5, 10.0),
                    "description": rel.description,
                    "edge_type": "relationship",
                    "count": rel.count,
                    "refer": rel.refer,  # 添加 refer 字段
                    "semantic_times": rel.semantic_times,  # 添加 semantic_times 字段
                }
            )

        return {"nodes": nodes, "links": links}

    def get_stats(self) -> dict:
        """获取统计信息"""
        if not self.sg:
            return {}

        # 获取基础统计信息
        stats = self.sg.get_statistics()

        # 获取图数据以计算所有边的数量（包括 has_class、instance_of_class 和 relationship）
        graph_data = self.get_graph_data()
        total_links = len(graph_data.get("links", []))

        # 更新 relationships 字段为所有边的数量，以匹配前端显示的连线
        if "graph" in stats:
            stats["graph"]["relationships"] = total_links

        return stats

    # ========== System 管理接口 ==========

    def get_system_classes(self) -> List[dict]:
        """获取所有类定义"""
        if not self.sg:
            return []

        classes = []
        for class_name in self.sg.system.get_all_classes():
            class_def = self.sg.system.get_class_definition(class_name)
            if class_def:
                classes.append(
                    {
                        "name": class_def.name,
                        "description": class_def.description,
                        "properties": [
                            {
                                "name": prop.name,
                                "description": prop.description,
                                "required": prop.required,
                                "value_required": prop.value_required,
                            }
                            for prop in class_def.properties
                        ],
                    }
                )
        return classes

    def get_class_definition(self, class_name: str) -> Optional[dict]:
        """获取指定类的定义"""
        if not self.sg:
            return None

        class_def = self.sg.system.get_class_definition(class_name)
        if not class_def:
            return None

        return {
            "name": class_def.name,
            "description": class_def.description,
            "properties": [
                {
                    "name": prop.name,
                    "description": prop.description,
                    "required": prop.required,
                    "value_required": prop.value_required,
                }
                for prop in class_def.properties
            ],
        }

    def add_class_to_system(
        self, class_name: str, description: str, properties: List[dict]
    ) -> dict:
        """
        添加新类到System

        Args:
            class_name: 类名称
            description: 类描述
            properties: 属性列表，格式为 [{"name": str, "description": str, "required": bool, "value_required": bool}]

        Returns:
            添加后的类定义
        """
        if not self.sg:
            raise Exception("SimpleGraph service not initialized")

        from src.models.entity import ClassDefinition, PropertyDefinition

        # 构建属性定义
        prop_defs = [
            PropertyDefinition(
                name=prop["name"],
                description=prop.get("description"),
                required=prop.get("required", False),
                value_required=prop.get("value_required", False),
            )
            for prop in properties
        ]

        # 创建类定义
        class_def = ClassDefinition(
            name=class_name, description=description, properties=prop_defs
        )

        # 添加到system
        self.sg.system.add_class_definition(class_def)

        logger.info(f"Added new class to system: {class_name}")

        return self.get_class_definition(class_name)

    def update_class_definition(
        self,
        class_name: str,
        description: Optional[str] = None,
        properties: Optional[List[dict]] = None,
    ) -> dict:
        """
        更新类定义（只能增强，不能删除）

        Args:
            class_name: 类名称
            description: 新描述（可选）
            properties: 要添加或更新的属性列表（可选）

        Returns:
            更新后的类定义
        """
        if not self.sg:
            raise Exception("SimpleGraph service not initialized")

        class_def = self.sg.system.get_class_definition(class_name)
        if not class_def:
            raise ValueError(f"Class '{class_name}' not found in system")

        from src.models.entity import ClassDefinition, PropertyDefinition

        # 构建更新的类定义
        updated_props = []
        if properties:
            updated_props = [
                PropertyDefinition(
                    name=prop["name"],
                    description=prop.get("description"),
                    required=prop.get("required", False),
                    value_required=prop.get("value_required", False),
                )
                for prop in properties
            ]

        updated_class = ClassDefinition(
            name=class_name,
            description=(
                description if description is not None else class_def.description
            ),
            properties=updated_props,
        )

        # 应用更新（会自动合并）
        self.sg.system.add_class_definition(updated_class)

        logger.info(f"Updated class definition: {class_name}")

        return self.get_class_definition(class_name)

    def add_property_to_class(
        self,
        class_name: str,
        property_name: str,
        description: Optional[str] = None,
        required: bool = False,
        value_required: bool = False,
    ) -> dict:
        """
        向类添加新属性

        Args:
            class_name: 类名称
            property_name: 属性名称
            description: 属性描述
            required: 是否为必选属性
            value_required: 属性值是否必填

        Returns:
            更新后的类定义
        """
        if not self.sg:
            raise Exception("SimpleGraph service not initialized")

        from src.models.entity import PropertyDefinition

        prop_def = PropertyDefinition(
            name=property_name,
            description=description,
            required=required,
            value_required=value_required,
        )

        self.sg.system.add_property(class_name, prop_def)

        logger.info(f"Added property '{property_name}' to class '{class_name}'")

        return self.get_class_definition(class_name)

    # ========== Entity 管理接口 ==========

    def get_all_entities(self) -> List[dict]:
        """获取所有实体的摘要信息"""
        if not self.sg:
            return []

        entities = []
        for entity in self.sg.graph.get_entities():
            entities.append(
                {
                    "name": entity.name,
                    "description": entity.description,
                    "classes": [c.class_name for c in entity.classes],
                    "created_at": (
                        entity.created_at.isoformat() if entity.created_at else None
                    ),
                    "updated_at": (
                        entity.updated_at.isoformat() if entity.updated_at else None
                    ),
                }
            )
        return entities

    def get_entity_detail(self, entity_name: str) -> Optional[dict]:
        """获取实体的详细信息"""
        if not self.sg:
            return None

        entity = self.sg.graph.get_entity(entity_name)
        if not entity:
            return None

        # 构建详细的类和属性信息
        classes_info = []
        for class_instance in entity.classes:
            class_def = self.sg.system.get_class_definition(class_instance.class_name)
            properties_info = []

            for prop_name, prop_value in class_instance.properties.items():
                # 获取属性定义
                prop_def = None
                if class_def:
                    prop_def = next(
                        (p for p in class_def.properties if p.name == prop_name), None
                    )

                properties_info.append(
                    {
                        "name": prop_name,
                        "value": prop_value.value,
                        "description": prop_def.description if prop_def else None,
                        "required": prop_def.required if prop_def else False,
                        "value_required": (
                            prop_def.value_required if prop_def else False
                        ),
                    }
                )

            classes_info.append(
                {
                    "class_name": class_instance.class_name,
                    "description": class_def.description if class_def else None,
                    "properties": properties_info,
                }
            )

        # 获取相关的关系
        relationships = []
        for rel in self.sg.graph.get_relationships():
            if rel.source == entity_name or rel.target == entity_name:
                relationships.append(
                    {
                        "source": rel.source,
                        "target": rel.target,
                        "description": rel.description,
                        "count": rel.count,
                        "refer": rel.refer,
                        "semantic_times": rel.semantic_times,  # 添加 semantic_times 字段
                    }
                )

        return {
            "name": entity.name,
            "description": entity.description,
            "classes": classes_info,
            "relationships": relationships,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }

    def update_entity(
        self,
        entity_name: str,
        description: Optional[str] = None,
        add_classes: Optional[List[str]] = None,
        remove_classes: Optional[List[str]] = None,
    ) -> dict:
        """
        更新实体信息

        Args:
            entity_name: 实体名称
            description: 新描述（可选）
            add_classes: 要添加的类列表（可选）
            remove_classes: 要移除的类列表（可选）

        Returns:
            更新后的实体详情
        """
        if not self.sg:
            raise Exception("SimpleGraph service not initialized")

        entity = self.sg.graph.get_entity(entity_name)
        if not entity:
            raise ValueError(f"Entity '{entity_name}' not found")

        # 更新描述
        if description is not None:
            entity.update_description(description)

        # 添加类
        if add_classes:
            for class_name in add_classes:
                if not entity.has_class(class_name):
                    entity.add_class(class_name, system=self.sg.system)

        # 移除类
        if remove_classes:
            for class_name in remove_classes:
                entity.remove_class(class_name)

        logger.info(f"Updated entity: {entity_name}")

        return self.get_entity_detail(entity_name)

    def update_entity_property(
        self, entity_name: str, class_name: str, property_name: str, value: str
    ) -> dict:
        """
        更新实体的属性值

        Args:
            entity_name: 实体名称
            class_name: 类名称
            property_name: 属性名称
            value: 新值

        Returns:
            更新后的实体详情
        """
        if not self.sg:
            raise Exception("SimpleGraph service not initialized")

        entity = self.sg.graph.get_entity(entity_name)
        if not entity:
            raise ValueError(f"Entity '{entity_name}' not found")

        # 设置属性值
        entity.set_property_value(
            class_name=class_name,
            property_name=property_name,
            value=value,
            system=self.sg.system,
        )

        logger.info(
            f"Updated property '{property_name}' of entity '{entity_name}' in class '{class_name}'"
        )

        return self.get_entity_detail(entity_name)

    def add_class_to_entity(
        self,
        entity_name: str,
        class_name: str,
        properties: Optional[Dict[str, str]] = None,
    ) -> dict:
        """
        为实体添加新类及其属性值

        Args:
            entity_name: 实体名称
            class_name: 要添加的类名称
            properties: 属性值字典（可选）

        Returns:
            更新后的实体详情
        """
        if not self.sg:
            raise Exception("SimpleGraph service not initialized")

        entity = self.sg.graph.get_entity(entity_name)
        if not entity:
            raise ValueError(f"Entity '{entity_name}' not found")

        # 添加类
        if not entity.has_class(class_name):
            entity.add_class(class_name, system=self.sg.system)

        # 设置属性值
        if properties:
            for prop_name, prop_value in properties.items():
                entity.set_property_value(
                    class_name=class_name,
                    property_name=prop_name,
                    value=prop_value,
                    system=self.sg.system,
                )

        logger.info(f"Added class '{class_name}' to entity '{entity_name}'")

        return self.get_entity_detail(entity_name)

    # ==================== 查询功能 ====================

    def search_keyword(
        self, keyword: str, fuzzy: bool = True, limit: Optional[int] = 50
    ) -> List[dict]:
        """
        关键词查询

        Args:
            keyword: 关键词
            fuzzy: 是否模糊查询（True=模糊，False=严格匹配）
            limit: 结果数量限制

        Returns:
            搜索结果列表
        """
        if not self.sg:
            return []

        results = self.sg.search_keyword(keyword, fuzzy, limit)

        # 转换为API返回格式
        return [
            {
                "result_type": result.result_type.value,
                "matched_text": result.matched_text,
                "context": result.context,
                "score": result.score,
            }
            for result in results
        ]

    def get_node_detail(self, node_id: str) -> Optional[dict]:
        """
        查询节点详细信息（含一层连接）

        Args:
            node_id: 节点ID（可以是实体名称、类节点ID"entity:class"、类主节点名称）

        Returns:
            节点详细信息
        """
        if not self.sg:
            return None

        node_detail = self.sg.get_node_detail(node_id)
        if not node_detail:
            return None

        return node_detail.to_dict()

    def get_entity_node_group(self, entity_name: str) -> Optional[dict]:
        """
        查询实体节点组（实体 + 其下所有实体类节点 + 一层连接）

        Args:
            entity_name: 实体名称

        Returns:
            实体节点组
        """
        if not self.sg:
            return None

        entity_group = self.sg.get_entity_node_group(entity_name)
        if not entity_group:
            return None

        return entity_group.to_dict()

    def get_class_node_group(self, class_name: str) -> Optional[dict]:
        """
        查询类节点组（类主节点 + 所有实例化该类的实体类节点 + 一层连接）

        Args:
            class_name: 类名称

        Returns:
            类节点组
        """
        if not self.sg:
            return None

        class_group = self.sg.get_class_node_group(class_name)
        if not class_group:
            return None

        return class_group.to_dict()

    async def shutdown(self):
        """关闭服务"""
        if self.sg:
            # 关闭前自动保存
            if self.auto_save_enabled:
                try:
                    await self.save_database()
                    logger.info("服务关闭前已自动保存数据库")
                except Exception as e:
                    logger.error(f"服务关闭前自动保存失败: {e}", exc_info=True)
            await self.sg.stop()

    def get_default_database_path(self) -> Path:
        """获取默认数据库路径"""
        return self.data_dir / "graph_database.pkl"

    async def save_database(self, file_path: Optional[Path] = None) -> dict:
        """
        保存数据库到文件

        Args:
            file_path: 保存路径，如果为None则使用默认路径

        Returns:
            保存结果信息
        """
        if not self.sg:
            raise Exception("SimpleGraph service not initialized")

        if file_path is None:
            file_path = self.get_default_database_path()

        logger.info(f"保存数据库到: {file_path}")

        try:
            # 保存graph
            self.sg.save(file_path)

            # 获取统计信息
            stats = self.sg.get_statistics()

            result = {
                "success": True,
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size if file_path.exists() else 0,
                "statistics": stats,
                "message": f"数据库已保存到 {file_path}",
            }

            logger.info(f"数据库保存成功: {file_path}")
            return result

        except Exception as e:
            logger.error(f"保存数据库失败: {e}", exc_info=True)
            raise Exception(f"保存数据库失败: {str(e)}")

    async def load_database(self, file_path: Optional[Path] = None) -> dict:
        """
        从文件加载数据库

        Args:
            file_path: 加载路径，如果为None则使用默认路径

        Returns:
            加载结果信息
        """
        if file_path is None:
            file_path = self.get_default_database_path()

        if not file_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {file_path}")

        logger.info(f"从文件加载数据库: {file_path}")

        try:
            # 如果服务已经运行，先停止
            if self.sg:
                await self.sg.stop()

            # 加载SimpleGraph
            self.sg = SimpleGraph.load(
                config_path=self.config_path,
                graph_path=file_path,
                max_concurrent_tasks=3,
                enable_smart_merge=True,
                progress_callback=self._on_progress,
            )

            # 启动服务
            await self.sg.start()

            # 获取统计信息
            stats = self.sg.get_statistics()

            result = {
                "success": True,
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size,
                "statistics": stats,
                "message": f"数据库已从 {file_path} 加载",
            }

            logger.info(f"数据库加载成功: {file_path}")
            return result

        except Exception as e:
            logger.error(f"加载数据库失败: {e}", exc_info=True)
            raise Exception(f"加载数据库失败: {str(e)}")

    async def list_database_files(self) -> List[dict]:
        """
        列出所有可用的数据库文件

        Returns:
            数据库文件列表
        """
        databases = []

        # 查找所有.pkl文件
        for file_path in self.data_dir.glob("*.pkl"):
            try:
                stat = file_path.stat()
                databases.append(
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "file_size": stat.st_size,
                        "modified_time": stat.st_mtime,
                        "is_default": file_path == self.get_default_database_path(),
                    }
                )
            except Exception as e:
                logger.warning(f"无法获取文件信息: {file_path}, 错误: {e}")

        # 按修改时间排序（最新的在前）
        databases.sort(key=lambda x: x["modified_time"], reverse=True)

        return databases

    def set_auto_save(self, enabled: bool):
        """
        设置是否启用自动保存

        Args:
            enabled: 是否启用
        """
        self.auto_save_enabled = enabled
        logger.info(f"自动保存已{'启用' if enabled else '禁用'}")

    async def create_new_database(self, file_name: Optional[str] = None) -> dict:
        """
        创建新的空数据库

        Args:
            file_name: 数据库文件名，如果为None则使用默认名称

        Returns:
            创建结果信息
        """
        logger.info("创建新的空数据库...")

        try:
            # 停止当前服务
            if self.sg:
                await self.sg.stop()

            # 创建新的SimpleGraph实例
            self.sg = SimpleGraph(
                config_path=self.config_path,
                max_concurrent_tasks=3,
                enable_smart_merge=True,
                progress_callback=self._on_progress,
            )
            await self.sg.start()

            # 确定保存路径
            if file_name:
                save_path = self.data_dir / file_name
            else:
                save_path = self.get_default_database_path()

            # 保存新数据库
            self.sg.save(save_path)

            stats = self.sg.get_statistics()

            result = {
                "success": True,
                "file_path": str(save_path),
                "file_name": save_path.name,
                "statistics": stats,
                "message": f"新数据库已创建并保存到 {save_path}",
            }

            logger.info(f"新数据库创建成功: {save_path}")
            return result

        except Exception as e:
            logger.error(f"创建新数据库失败: {e}", exc_info=True)
            raise Exception(f"创建新数据库失败: {str(e)}")

    async def delete_database(self, file_name: str) -> dict:
        """
        删除数据库文件

        Args:
            file_name: 要删除的文件名

        Returns:
            删除结果
        """
        file_path = self.data_dir / file_name

        if not file_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {file_name}")

        # 检查是否是当前正在使用的默认数据库
        if file_path == self.get_default_database_path():
            raise ValueError("不能删除当前正在使用的默认数据库")

        try:
            file_path.unlink()
            logger.info(f"数据库文件已删除: {file_path}")

            return {
                "success": True,
                "file_name": file_name,
                "message": f"数据库文件 {file_name} 已删除",
            }

        except Exception as e:
            logger.error(f"删除数据库失败: {e}", exc_info=True)
            raise Exception(f"删除数据库失败: {str(e)}")

    async def rename_database(self, old_name: str, new_name: str) -> dict:
        """
        重命名数据库文件

        Args:
            old_name: 旧文件名
            new_name: 新文件名

        Returns:
            重命名结果
        """
        old_path = self.data_dir / old_name
        new_path = self.data_dir / new_name

        if not old_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {old_name}")

        if new_path.exists():
            raise ValueError(f"目标文件名已存在: {new_name}")

        try:
            old_path.rename(new_path)
            logger.info(f"数据库文件已重命名: {old_name} -> {new_name}")

            return {
                "success": True,
                "old_name": old_name,
                "new_name": new_name,
                "new_path": str(new_path),
                "message": f"数据库文件已重命名为 {new_name}",
            }

        except Exception as e:
            logger.error(f"重命名数据库失败: {e}", exc_info=True)
            raise Exception(f"重命名数据库失败: {str(e)}")


# 全局单例
graph_service = GraphService()
