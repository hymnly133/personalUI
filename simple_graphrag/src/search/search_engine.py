"""
知识图谱搜索引擎

提供多样化的查询功能：
1. 关键词查询（模糊/严格匹配）
2. 节点详细信息查询
3. 实体节点组查询
4. 类节点组查询
"""

from typing import List, Dict, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re
from ..models.entity import Entity, ClassNode, ClassMasterNode, System
from ..models.relationship import Relationship
from ..models.graph import Graph
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SearchResultType(Enum):
    """搜索结果类型"""

    ENTITY = "entity"  # 实体
    ENTITY_NAME = "entity_name"  # 实体名称
    ENTITY_DESCRIPTION = "entity_description"  # 实体描述
    CLASS_NODE = "class_node"  # 实体类节点（entity:class）
    CLASS_MASTER_NODE = "class_master_node"  # 类主节点
    CLASS_NAME = "class_name"  # 类名称
    CLASS_DESCRIPTION = "class_description"  # 类描述
    PROPERTY_NAME = "property_name"  # 属性名称
    PROPERTY_VALUE = "property_value"  # 属性值
    RELATIONSHIP = "relationship"  # 关系
    RELATIONSHIP_DESCRIPTION = "relationship_description"  # 关系描述
    RELATIONSHIP_REFER = "relationship_refer"  # 关系refer字段


@dataclass
class SearchResult:
    """搜索结果"""

    result_type: SearchResultType
    matched_text: str  # 匹配到的文本
    matched_item: Any  # 匹配到的对象（Entity/Relationship/ClassNode等）
    context: Dict[str, Any] = field(default_factory=dict)  # 上下文信息
    score: float = 1.0  # 相关度得分（0-1）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于JSON序列化"""
        # 将matched_item转换为可序列化的格式
        matched_item_data = None
        if isinstance(self.matched_item, str):
            matched_item_data = self.matched_item
        elif hasattr(self.matched_item, "name"):
            # Entity或ClassNode等有name属性的对象
            matched_item_data = self.matched_item.name
        elif hasattr(self.matched_item, "node_id"):
            # 有node_id的对象
            matched_item_data = self.matched_item.node_id
        else:
            # 其他情况，尝试转换为字符串
            matched_item_data = str(self.matched_item)

        return {
            "result_type": (
                self.result_type.value
                if isinstance(self.result_type, SearchResultType)
                else str(self.result_type)
            ),
            "matched_text": self.matched_text,
            "matched_item": matched_item_data,
            "context": self.context,
            "score": self.score,
        }


@dataclass
class EntityNodeGroup:
    """
    实体节点组：一个实体节点本身 + 其下所有实体类节点

    例如："小红书"实体包含：
    - 实体节点: 小红书
    - 实体类节点: 小红书:购物平台, 小红书:内容平台, 小红书:可启动应用
    """

    entity: Entity  # 实体节点
    class_nodes: List[ClassNode]  # 实体的所有类节点
    one_hop_relationships: List[Relationship] = field(
        default_factory=list
    )  # 一层连接的关系

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "entity": {
                "name": self.entity.name,
                "description": self.entity.description,
                "classes": [c.class_name for c in self.entity.classes],
                "properties": {
                    class_instance.class_name: {
                        prop_name: prop_value.value
                        for prop_name, prop_value in class_instance.properties.items()
                    }
                    for class_instance in self.entity.classes
                },
                "created_at": (
                    self.entity.created_at.isoformat()
                    if self.entity.created_at
                    else None
                ),
                "updated_at": (
                    self.entity.updated_at.isoformat()
                    if self.entity.updated_at
                    else None
                ),
            },
            "class_nodes": [
                {
                    "node_id": cn.node_id,
                    "entity_name": cn.entity_name,
                    "class_name": cn.class_name,
                    "description": cn.description,
                }
                for cn in self.class_nodes
            ],
            "one_hop_relationships": [
                {
                    "source": rel.source,
                    "target": rel.target,
                    "description": rel.description,
                    "count": rel.count,
                    "refer": rel.refer,
                }
                for rel in self.one_hop_relationships
            ],
            "statistics": {
                "class_nodes_count": len(self.class_nodes),
                "relationships_count": len(self.one_hop_relationships),
            },
        }


@dataclass
class ClassNodeGroup:
    """
    类节点组：一个类的类主节点 + 所有实例化该类的实体类节点

    例如："购物平台"类包含：
    - 类主节点: 购物平台
    - 实体类节点: 小红书:购物平台, 淘宝:购物平台, 京东:购物平台
    """

    class_master_node: ClassMasterNode  # 类主节点
    class_nodes: List[ClassNode]  # 所有实例化该类的实体类节点
    one_hop_relationships: List[Relationship] = field(
        default_factory=list
    )  # 一层连接的关系

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "class_master_node": {
                "class_name": self.class_master_node.class_name,
                "description": self.class_master_node.description,
            },
            "class_nodes": [
                {
                    "node_id": cn.node_id,
                    "entity_name": cn.entity_name,
                    "class_name": cn.class_name,
                    "description": cn.description,
                }
                for cn in self.class_nodes
            ],
            "one_hop_relationships": [
                {
                    "source": rel.source,
                    "target": rel.target,
                    "description": rel.description,
                    "count": rel.count,
                    "refer": rel.refer,
                }
                for rel in self.one_hop_relationships
            ],
            "statistics": {
                "instances_count": len(self.class_nodes),
                "relationships_count": len(self.one_hop_relationships),
            },
        }


@dataclass
class NodeDetail:
    """节点详细信息（含一层连接）"""

    node_id: str  # 节点ID
    node_type: str  # 节点类型：entity/class_node/class_master_node
    node_info: Dict[str, Any]  # 节点本身的信息
    one_hop_relationships: List[Dict[str, Any]]  # 一层连接的关系
    one_hop_neighbors: List[Dict[str, Any]]  # 一层邻居节点

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "node_info": self.node_info,
            "one_hop_relationships": self.one_hop_relationships,
            "one_hop_neighbors": self.one_hop_neighbors,
            "statistics": {
                "relationships_count": len(self.one_hop_relationships),
                "neighbors_count": len(self.one_hop_neighbors),
            },
        }


class SearchEngine:
    """知识图谱搜索引擎"""

    def __init__(self, graph: Graph):
        """
        初始化搜索引擎

        Args:
            graph: 知识图谱对象
        """
        self.graph = graph
        self.system = graph.system
        logger.info("搜索引擎初始化完成")

    # ==================== 关键词查询 ====================

    def search_keyword(
        self, keyword: str, fuzzy: bool = True, limit: Optional[int] = None
    ) -> List[SearchResult]:
        """
        关键词查询

        Args:
            keyword: 关键词
            fuzzy: 是否模糊查询（True=模糊，False=严格匹配）
            limit: 结果数量限制

        Returns:
            搜索结果列表
        """
        logger.debug(f"开始关键词查询: '{keyword}' (模糊={fuzzy})")

        results: List[SearchResult] = []

        # 1. 搜索实体
        results.extend(self._search_entities(keyword, fuzzy))

        # 2. 搜索类节点
        results.extend(self._search_class_nodes(keyword, fuzzy))

        # 3. 搜索类主节点
        results.extend(self._search_class_master_nodes(keyword, fuzzy))

        # 4. 搜索关系
        results.extend(self._search_relationships(keyword, fuzzy))

        # 5. 搜索属性
        results.extend(self._search_properties(keyword, fuzzy))

        # 智能去重：移除已包含在高级项目中的子项目
        results = self._deduplicate_results(results)

        # 按相关度得分排序
        results.sort(key=lambda x: x.score, reverse=True)

        # 限制结果数量
        if limit:
            results = results[:limit]

        logger.info(f"关键词查询完成: 找到 {len(results)} 个结果（去重后）")
        return results

    def _search_entities(self, keyword: str, fuzzy: bool) -> List[SearchResult]:
        """搜索实体"""
        results = []
        for entity in self.graph.get_entities():
            # 搜索实体名称
            if self._match(keyword, entity.name, fuzzy):
                results.append(
                    SearchResult(
                        result_type=SearchResultType.ENTITY_NAME,
                        matched_text=entity.name,
                        matched_item=entity,
                        context={"entity_name": entity.name},
                        score=self._calculate_score(keyword, entity.name, fuzzy),
                    )
                )

            # 搜索实体描述
            if entity.description and self._match(keyword, entity.description, fuzzy):
                results.append(
                    SearchResult(
                        result_type=SearchResultType.ENTITY_DESCRIPTION,
                        matched_text=entity.description,
                        matched_item=entity,
                        context={
                            "entity_name": entity.name,
                            "description": entity.description,
                        },
                        score=self._calculate_score(keyword, entity.description, fuzzy),
                    )
                )

        return results

    def _search_class_nodes(self, keyword: str, fuzzy: bool) -> List[SearchResult]:
        """搜索实体类节点"""
        results = []
        for class_node in self.graph.get_class_nodes():
            # 搜索类节点ID
            if self._match(keyword, class_node.node_id, fuzzy):
                results.append(
                    SearchResult(
                        result_type=SearchResultType.CLASS_NODE,
                        matched_text=class_node.node_id,
                        matched_item=class_node,
                        context={
                            "node_id": class_node.node_id,
                            "entity_name": class_node.entity_name,
                            "class_name": class_node.class_name,
                        },
                        score=self._calculate_score(keyword, class_node.node_id, fuzzy),
                    )
                )

            # 搜索类节点描述
            if class_node.description and self._match(
                keyword, class_node.description, fuzzy
            ):
                results.append(
                    SearchResult(
                        result_type=SearchResultType.CLASS_NODE,
                        matched_text=class_node.description,
                        matched_item=class_node,
                        context={
                            "node_id": class_node.node_id,
                            "description": class_node.description,
                        },
                        score=self._calculate_score(
                            keyword, class_node.description, fuzzy
                        ),
                    )
                )

        return results

    def _search_class_master_nodes(
        self, keyword: str, fuzzy: bool
    ) -> List[SearchResult]:
        """搜索类主节点"""
        results = []
        for class_master in self.graph.get_class_master_nodes():
            # 搜索类名称
            if self._match(keyword, class_master.class_name, fuzzy):
                results.append(
                    SearchResult(
                        result_type=SearchResultType.CLASS_NAME,
                        matched_text=class_master.class_name,
                        matched_item=class_master,
                        context={"class_name": class_master.class_name},
                        score=self._calculate_score(
                            keyword, class_master.class_name, fuzzy
                        ),
                    )
                )

            # 搜索类描述
            if class_master.description and self._match(
                keyword, class_master.description, fuzzy
            ):
                results.append(
                    SearchResult(
                        result_type=SearchResultType.CLASS_DESCRIPTION,
                        matched_text=class_master.description,
                        matched_item=class_master,
                        context={
                            "class_name": class_master.class_name,
                            "description": class_master.description,
                        },
                        score=self._calculate_score(
                            keyword, class_master.description, fuzzy
                        ),
                    )
                )

        return results

    def _search_relationships(self, keyword: str, fuzzy: bool) -> List[SearchResult]:
        """搜索关系"""
        results = []
        for relationship in self.graph.get_relationships():
            # 搜索关系描述
            if self._match(keyword, relationship.description, fuzzy):
                results.append(
                    SearchResult(
                        result_type=SearchResultType.RELATIONSHIP_DESCRIPTION,
                        matched_text=relationship.description,
                        matched_item=relationship,
                        context={
                            "source": relationship.source,
                            "target": relationship.target,
                            "description": relationship.description,
                        },
                        score=self._calculate_score(
                            keyword, relationship.description, fuzzy
                        ),
                    )
                )

            # 搜索关系的refer字段
            for refer_item in relationship.refer:
                if self._match(keyword, refer_item, fuzzy):
                    results.append(
                        SearchResult(
                            result_type=SearchResultType.RELATIONSHIP_REFER,
                            matched_text=refer_item,
                            matched_item=relationship,
                            context={
                                "source": relationship.source,
                                "target": relationship.target,
                                "refer": refer_item,
                            },
                            score=self._calculate_score(keyword, refer_item, fuzzy),
                        )
                    )

        return results

    def _search_properties(self, keyword: str, fuzzy: bool) -> List[SearchResult]:
        """搜索属性"""
        results = []

        # 搜索类定义中的属性名称
        for class_name in self.system.get_all_classes():
            class_def = self.system.get_class_definition(class_name)
            if not class_def:
                continue

            for prop_def in class_def.properties:
                # 搜索属性名称
                if self._match(keyword, prop_def.name, fuzzy):
                    results.append(
                        SearchResult(
                            result_type=SearchResultType.PROPERTY_NAME,
                            matched_text=prop_def.name,
                            matched_item=prop_def,
                            context={
                                "class_name": class_name,
                                "property_name": prop_def.name,
                                "description": prop_def.description,
                            },
                            score=self._calculate_score(keyword, prop_def.name, fuzzy),
                        )
                    )

        # 搜索实体实例中的属性值
        for entity in self.graph.get_entities():
            for class_instance in entity.classes:
                for prop_name, prop_value in class_instance.properties.items():
                    if prop_value.value and self._match(
                        keyword, prop_value.value, fuzzy
                    ):
                        results.append(
                            SearchResult(
                                result_type=SearchResultType.PROPERTY_VALUE,
                                matched_text=prop_value.value,
                                matched_item=prop_value,
                                context={
                                    "entity_name": entity.name,
                                    "class_name": class_instance.class_name,
                                    "property_name": prop_name,
                                    "property_value": prop_value.value,
                                },
                                score=self._calculate_score(
                                    keyword, prop_value.value, fuzzy
                                ),
                            )
                        )

        return results

    def _deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        智能去重：移除已包含在高级项目中的子项目

        层级关系：
        - 实体节点（高级）> 实体描述、实体属性值（次级）
        - 类节点（高级）> 类节点描述（次级）
        - 类主节点（高级）> 类主节点描述（次级）
        - 关系（高级）> 关系refer字段（次级）

        如果高级项目被搜索到，则移除其对应的次级项目，
        因为高级项目已经包含了完整信息。
        """
        # 收集所有高级项目
        found_entities = set()  # 实体名称
        found_class_nodes = set()  # 类节点ID（entity:class格式）
        found_class_masters = set()  # 类主节点名称
        found_relationships = set()  # 关系（source-target元组）

        for result in results:
            if result.result_type == SearchResultType.ENTITY_NAME:
                # 收集实体节点
                entity_name = result.context.get("entity_name")
                if entity_name:
                    found_entities.add(entity_name)

            elif result.result_type == SearchResultType.CLASS_NODE:
                # 收集类节点（仅当匹配的是node_id，而不是描述）
                node_id = result.context.get("node_id")
                if node_id and result.matched_text == node_id:
                    found_class_nodes.add(node_id)

            elif result.result_type == SearchResultType.CLASS_NAME:
                # 收集类主节点
                class_name = result.context.get("class_name")
                if class_name:
                    found_class_masters.add(class_name)

            elif result.result_type == SearchResultType.RELATIONSHIP_DESCRIPTION:
                # 收集关系
                source = result.context.get("source")
                target = result.context.get("target")
                if source and target:
                    found_relationships.add((source, target))

        # 过滤次级项目
        filtered_results = []
        removed_count = 0

        for result in results:
            should_keep = True

            # 1. 如果找到了实体节点，移除该实体的描述和属性值
            if result.result_type == SearchResultType.ENTITY_DESCRIPTION:
                entity_name = result.context.get("entity_name")
                if entity_name in found_entities:
                    should_keep = False
                    removed_count += 1
                    logger.debug(
                        f"移除冗余项：实体 '{entity_name}' 的描述" f"（已有实体节点）"
                    )

            elif result.result_type == SearchResultType.PROPERTY_VALUE:
                entity_name = result.context.get("entity_name")
                if entity_name in found_entities:
                    should_keep = False
                    removed_count += 1
                    logger.debug(
                        f"移除冗余项：实体 '{entity_name}' 的属性值" f"（已有实体节点）"
                    )

            # 2. 如果找到了类节点，移除该类节点的描述
            # （这里需要判断是否是描述匹配而不是node_id匹配）
            elif result.result_type == SearchResultType.CLASS_NODE:
                node_id = result.context.get("node_id")
                # 如果node_id在found中，但matched_text不是node_id，说明是描述匹配
                if node_id in found_class_nodes and result.matched_text != node_id:
                    should_keep = False
                    removed_count += 1
                    logger.debug(
                        f"移除冗余项：类节点 '{node_id}' 的描述" f"（已有类节点）"
                    )

            # 3. 如果找到了类主节点，移除该类的描述
            elif result.result_type == SearchResultType.CLASS_DESCRIPTION:
                class_name = result.context.get("class_name")
                if class_name in found_class_masters:
                    should_keep = False
                    removed_count += 1
                    logger.debug(
                        f"移除冗余项：类 '{class_name}' 的描述" f"（已有类主节点）"
                    )

            # 4. 如果找到了关系，移除该关系的refer字段
            elif result.result_type == SearchResultType.RELATIONSHIP_REFER:
                source = result.context.get("source")
                target = result.context.get("target")
                if (source, target) in found_relationships:
                    should_keep = False
                    removed_count += 1
                    logger.debug(
                        f"移除冗余项：关系 '{source}->{target}' 的refer字段"
                        f"（已有关系）"
                    )

            if should_keep:
                filtered_results.append(result)

        if removed_count > 0:
            logger.info(f"智能去重：移除了 {removed_count} 个冗余项")

        return filtered_results

    def _match(self, keyword: str, text: str, fuzzy: bool) -> bool:
        """
        匹配文本

        Args:
            keyword: 关键词
            text: 待匹配文本
            fuzzy: 是否模糊匹配

        Returns:
            是否匹配
        """
        if not text:
            return False

        keyword_lower = keyword.lower()
        text_lower = text.lower()

        if fuzzy:
            # 模糊匹配：包含即可
            return keyword_lower in text_lower
        else:
            # 严格匹配：完全相等
            return keyword_lower == text_lower

    def _calculate_score(self, keyword: str, text: str, fuzzy: bool) -> float:
        """
        计算相关度得分

        Args:
            keyword: 关键词
            text: 匹配到的文本
            fuzzy: 是否模糊匹配

        Returns:
            相关度得分（0-1）
        """
        if not text:
            return 0.0

        keyword_lower = keyword.lower()
        text_lower = text.lower()

        if not fuzzy:
            # 严格匹配：完全相等得1分
            return 1.0 if keyword_lower == text_lower else 0.0

        # 模糊匹配：计算相似度
        if keyword_lower == text_lower:
            return 1.0  # 完全匹配

        if text_lower.startswith(keyword_lower):
            return 0.9  # 前缀匹配

        # 包含匹配：根据关键词在文本中的位置和长度比例计算得分
        keyword_len = len(keyword_lower)
        text_len = len(text_lower)
        keyword_ratio = keyword_len / text_len if text_len > 0 else 0

        # 基础得分：关键词占比
        base_score = min(keyword_ratio * 2, 0.8)

        return base_score

    # ==================== 节点详情查询 ====================

    def get_node_detail(self, node_id: str) -> Optional[NodeDetail]:
        """
        获取节点详细信息（含一层连接）

        Args:
            node_id: 节点ID（可以是实体名称、类节点ID"entity:class"、类主节点名称）

        Returns:
            节点详细信息，如果节点不存在返回None
        """
        logger.debug(f"查询节点详情: {node_id}")

        # 判断节点类型
        if ":" in node_id:
            # 类节点格式：entity:class
            return self._get_class_node_detail(node_id)
        else:
            # 可能是实体节点或类主节点
            entity = self.graph.get_entity(node_id)
            if entity:
                return self._get_entity_node_detail(node_id)

            # 检查是否是类主节点
            class_master = self.graph.get_class_master_node(node_id)
            if class_master:
                return self._get_class_master_node_detail(node_id)

        logger.warning(f"节点不存在: {node_id}")
        return None

    def _get_entity_node_detail(self, entity_name: str) -> Optional[NodeDetail]:
        """获取实体节点详情"""
        entity = self.graph.get_entity(entity_name)
        if not entity:
            return None

        # 获取一层关系
        relationships = self.graph.get_relationships(entity_name)

        # 获取邻居节点
        neighbors = set()
        for rel in relationships:
            if rel.source.upper() == entity_name.upper():
                neighbors.add(rel.target)
            if rel.target.upper() == entity_name.upper():
                neighbors.add(rel.source)

        return NodeDetail(
            node_id=entity_name,
            node_type="entity",
            node_info={
                "name": entity.name,
                "description": entity.description,
                "classes": [c.class_name for c in entity.classes],
                "properties": {
                    class_instance.class_name: {
                        prop_name: prop_value.value
                        for prop_name, prop_value in class_instance.properties.items()
                    }
                    for class_instance in entity.classes
                },
            },
            one_hop_relationships=[
                {
                    "source": rel.source,
                    "target": rel.target,
                    "description": rel.description,
                    "count": rel.count,
                    "refer": rel.refer,
                }
                for rel in relationships
            ],
            one_hop_neighbors=[{"node_id": neighbor} for neighbor in neighbors],
        )

    def _get_class_node_detail(self, node_id: str) -> Optional[NodeDetail]:
        """获取实体类节点详情"""
        parts = node_id.split(":")
        if len(parts) != 2:
            return None

        entity_name, class_name = parts
        class_node = self.graph.get_class_node(entity_name, class_name)
        if not class_node:
            return None

        # 获取一层关系
        relationships = self.graph.get_relationships(node_id)

        # 获取邻居节点
        neighbors = set()
        for rel in relationships:
            if rel.source.upper() == node_id.upper():
                neighbors.add(rel.target)
            if rel.target.upper() == node_id.upper():
                neighbors.add(rel.source)

        # 获取实体的类实例信息（包含属性）
        entity = self.graph.get_entity(entity_name)
        class_instance = entity.get_class_instance(class_name) if entity else None
        properties = {}
        if class_instance:
            properties = {
                prop_name: prop_value.value
                for prop_name, prop_value in class_instance.properties.items()
            }

        return NodeDetail(
            node_id=node_id,
            node_type="class_node",
            node_info={
                "node_id": class_node.node_id,
                "entity_name": class_node.entity_name,
                "class_name": class_node.class_name,
                "description": class_node.description,
                "properties": properties,
            },
            one_hop_relationships=[
                {
                    "source": rel.source,
                    "target": rel.target,
                    "description": rel.description,
                    "count": rel.count,
                    "refer": rel.refer,
                }
                for rel in relationships
            ],
            one_hop_neighbors=[{"node_id": neighbor} for neighbor in neighbors],
        )

    def _get_class_master_node_detail(self, class_name: str) -> Optional[NodeDetail]:
        """获取类主节点详情"""
        class_master = self.graph.get_class_master_node(class_name)
        if not class_master:
            return None

        # 获取一层关系（连接到类主节点的关系）
        relationships = self.graph.get_relationships(class_name)

        # 获取邻居节点
        neighbors = set()
        for rel in relationships:
            if rel.source.upper() == class_name.upper():
                neighbors.add(rel.target)
            if rel.target.upper() == class_name.upper():
                neighbors.add(rel.source)

        # 获取类定义信息
        class_def = self.system.get_class_definition(class_name)
        properties_info = []
        if class_def:
            properties_info = [
                {
                    "name": prop.name,
                    "description": prop.description,
                    "required": prop.required,
                    "value_required": prop.value_required,
                }
                for prop in class_def.properties
            ]

        return NodeDetail(
            node_id=class_name,
            node_type="class_master_node",
            node_info={
                "class_name": class_master.class_name,
                "description": class_master.description,
                "properties": properties_info,
            },
            one_hop_relationships=[
                {
                    "source": rel.source,
                    "target": rel.target,
                    "description": rel.description,
                    "count": rel.count,
                    "refer": rel.refer,
                }
                for rel in relationships
            ],
            one_hop_neighbors=[{"node_id": neighbor} for neighbor in neighbors],
        )

    # ==================== 实体节点组查询 ====================

    def get_entity_node_group(self, entity_name: str) -> Optional[EntityNodeGroup]:
        """
        获取实体节点组（实体 + 其下所有实体类节点 + 一层连接）

        Args:
            entity_name: 实体名称

        Returns:
            实体节点组，如果实体不存在返回None
        """
        logger.debug(f"查询实体节点组: {entity_name}")

        entity = self.graph.get_entity(entity_name)
        if not entity:
            logger.warning(f"实体不存在: {entity_name}")
            return None

        # 获取该实体的所有类节点
        class_nodes = self.graph.get_class_nodes(entity_name)

        # 获取一层关系（包括实体节点和类节点的关系）
        relationships = set()

        # 实体节点的关系
        for rel in self.graph.get_relationships(entity_name):
            relationships.add(rel)

        # 类节点的关系
        for class_node in class_nodes:
            for rel in self.graph.get_relationships(class_node.node_id):
                relationships.add(rel)

        return EntityNodeGroup(
            entity=entity,
            class_nodes=class_nodes,
            one_hop_relationships=list(relationships),
        )

    # ==================== 类节点组查询 ====================

    def get_class_node_group(self, class_name: str) -> Optional[ClassNodeGroup]:
        """
        获取类节点组（类主节点 + 所有实例化该类的实体类节点 + 一层连接）

        Args:
            class_name: 类名称

        Returns:
            类节点组，如果类不存在返回None
        """
        logger.debug(f"查询类节点组: {class_name}")

        class_master = self.graph.get_class_master_node(class_name)
        if not class_master:
            logger.warning(f"类不存在: {class_name}")
            return None

        # 获取所有实例化该类的实体类节点
        class_nodes = []
        for class_node in self.graph.get_class_nodes():
            if class_node.class_name.upper() == class_name.upper():
                class_nodes.append(class_node)

        # 获取一层关系（包括类主节点和类节点的关系）
        relationships = set()

        # 类主节点的关系
        for rel in self.graph.get_relationships(class_name):
            relationships.add(rel)

        # 类节点的关系
        for class_node in class_nodes:
            for rel in self.graph.get_relationships(class_node.node_id):
                relationships.add(rel)

        return ClassNodeGroup(
            class_master_node=class_master,
            class_nodes=class_nodes,
            one_hop_relationships=list(relationships),
        )
