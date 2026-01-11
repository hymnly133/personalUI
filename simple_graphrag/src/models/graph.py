"""
图数据模型
"""

from typing import Dict, Set, List, Optional
from collections import defaultdict
import pickle
from pathlib import Path
from datetime import datetime

from .entity import Entity, ClassNode, ClassMasterNode, System
from .relationship import Relationship
from ..utils.logger import get_logger

logger = get_logger(__name__)


class Graph:
    """
    Graph：使用某个 System（抽象架构）形成具体实例

    节点类型：
    - 类主（class master）：ClassMasterNode，表示“类本身”
    - 实体（entity）：Entity，表示具体对象
    - 实体类（entity:class）：ClassNode，表示“某实体的某类”作为独立节点

    显式关系（Relationship）可以连接任意两类节点。
    """

    def __init__(
        self, system: Optional[System] = None, include_predefined_entities: bool = True
    ):
        """初始化图（绑定 system 配置）"""
        self.system: System = system or System()
        self._entities: Dict[str, Entity] = {}  # 中心节点字典，key为实体名称（大写）
        self._class_nodes: Dict[str, ClassNode] = (
            {}
        )  # 类节点字典，key为 node_id（大写）
        self._relationships: Set[Relationship] = set()  # 关系集合
        self._entity_relationships: Dict[str, Set[str]] = defaultdict(
            set
        )  # 节点到关系的映射（包括实体、类节点、类主节点）
        from ..search.search_engine import SearchEngine

        self._search_engine = SearchEngine(self)  # 搜索引擎引用（由外部设置）

        # Graph 内部维持对 system 的引用；且“类本身”的真相只在 system 中
        # （Graph 不维护等价的 class_master_nodes 状态）
        self.system.subscribe_class_added(self._on_system_class_added)

        # 可选：把 system 内置实体注入图（系统级“始终可用”的实体）
        if include_predefined_entities:
            for predefined in self.system.predefined_entities:
                try:
                    self.add_entity(
                        predefined.to_entity(system=self.system),
                        strict_validation=False,
                    )
                except Exception:
                    # 预定义实体不应阻塞图初始化
                    logger.warning(
                        f"预定义实体注入失败: {predefined.name}", exc_info=True
                    )

    # -----------------------------
    # 原子功能：system 动态扩展后的回调（Graph 不缓存“类本身”，这里主要用于日志/未来扩展）
    # -----------------------------

    def _on_system_class_added(self, class_def) -> None:
        # 这里不需要同步任何“类主节点缓存”，因为 Graph 每次都直接用 system
        logger.debug(f"System 新增/扩展类定义: {class_def.name}")

    # -----------------------------
    # 原子功能：Graph 对 system 的便捷操作（只增不删）
    # -----------------------------

    def add_class_definition(self, class_def) -> None:
        """向 graph 绑定的 system 动态添加/扩展类定义（只增不删）"""
        self.system.add_class_definition(class_def)

    def define_class_from_dict(self, class_name: str, config: dict) -> None:
        """便捷：从 {description, properties:[...]} 定义/扩展一个类"""
        from .entity import ClassDefinition

        self.system.add_class_definition(
            ClassDefinition.from_dict({"name": class_name, **(config or {})})
        )

    # -----------------------------
    # 原子功能：在现有图中“实例化类”（实体/实体:类节点）
    # -----------------------------

    def create_entity(
        self,
        name: str,
        description: str,
        class_names: Optional[List[str]] = None,
        class_properties: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
        strict_validation: bool = True,
    ) -> Entity:
        """
        创建并加入一个实体（可同时实例化多个类，并填充属性）

        - class_names: ["购物平台", "公司", ...]
        - class_properties: {"购物平台": {"成立时间": "2013"}, ...}
        """
        e = Entity(name=name, description=description)
        # 先绑定到 Graph，后续操作自动使用 graph.system
        e._graph = self
        for cn in class_names or []:
            e.add_class(cn)  # 不再需要传 system
            for prop_name, value in (class_properties or {}).get(cn, {}).items():
                e.set_property_value(cn, prop_name, value)  # 不再需要传 system
        return self.add_entity(e, strict_validation=strict_validation)

    def add_class_to_entity(
        self,
        entity_name: str,
        class_name: str,
        properties: Optional[Dict[str, Optional[str]]] = None,
        strict_validation: bool = True,
    ) -> Entity:
        """
        给已存在实体新增一个类实例，并创建对应的实体类节点（entity:class）
        """
        e = self.get_entity(entity_name)
        if not e:
            raise ValueError(f"实体 '{entity_name}' 不存在于图中")
        # 实体已经绑定到 graph，不需要传 system
        e.add_class(class_name)
        for prop_name, value in (properties or {}).items():
            e.set_property_value(class_name, prop_name, value)
        # 重新校验/修复（尤其是 required/value_required）
        e.validate_against_system(self.system, strict=strict_validation)
        # 补齐类节点
        self._create_or_update_class_node(e, class_name)
        return e

    def add_entity(self, entity: Entity, strict_validation: bool = True) -> Entity:
        """
        添加实体到图中

        Args:
            entity: 要添加的实体
            strict_validation: 是否严格按 system 验证实体类/属性

        Returns:
            返回图中的实体（可能是新添加的或已存在的）
        """
        # 按 system 校验/修复实体
        entity.validate_against_system(self.system, strict=strict_validation)

        # 绑定实体到当前 Graph（让 Entity 的后续操作自动使用 graph.system）
        entity._graph = self

        key = entity.name.upper()

        if key in self._entities:
            # 如果实体已存在，更新描述和类
            existing_entity = self._entities[key]
            class_names = [c.class_name for c in entity.classes]
            logger.debug(f"更新已存在的实体: {entity.name} (类: {class_names})")
            existing_entity.update_description(entity.description)
            # 合并类（去重）
            for class_instance in entity.classes:
                existing_class = existing_entity.get_class_instance(
                    class_instance.class_name
                )
                if existing_class:
                    # 如果类已存在，合并属性
                    for prop_name, prop_value in class_instance.properties.items():
                        existing_class.set_property(prop_name, prop_value.value)
                else:
                    # 如果类不存在，添加该类
                    try:
                        # 实体已经绑定到 graph，不需要传 system
                        existing_entity.add_class(class_instance.class_name)
                        new_class = existing_entity.get_class_instance(
                            class_instance.class_name
                        )
                        if new_class:
                            for (
                                prop_name,
                                prop_value,
                            ) in class_instance.properties.items():
                                new_class.set_property(prop_name, prop_value.value)
                        # 创建或更新类节点
                        self._create_or_update_class_node(
                            existing_entity, class_instance.class_name
                        )
                    except ValueError:
                        # 如果类验证失败，记录警告但继续
                        logger.warning(
                            f"跳过无效类 '{class_instance.class_name}' 添加到实体 '{entity.name}'"
                        )
            return existing_entity
        else:
            # 添加新实体
            class_names = [c.class_name for c in entity.classes]
            logger.debug(f"添加新实体: {entity.name} (类: {class_names})")
            self._entities[key] = entity
            # 为每个类创建类节点
            for class_instance in entity.classes:
                self._create_or_update_class_node(entity, class_instance.class_name)
            return entity

    def _create_or_update_class_node(
        self, entity: Entity, class_name: str
    ) -> ClassNode:
        """
        创建或更新类节点

        Args:
            entity: 实体对象
            class_name: 类名称

        Returns:
            创建的类节点
        """
        class_def = self.system.get_class_definition(class_name)
        description = class_def.description if class_def else None

        class_node = ClassNode(
            entity_name=entity.name,
            class_name=class_name,
            description=description or f"{entity.name}的{class_name}类",
        )

        node_key = class_node.node_id.upper()
        self._class_nodes[node_key] = class_node
        logger.debug(f"创建类节点: {class_node.node_id}")
        return class_node

    def add_class_node(self, class_node: ClassNode) -> ClassNode:
        """
        添加类节点到图中

        Args:
            class_node: 要添加的类节点

        Returns:
            返回图中的类节点（可能是新添加的或已存在的）
        """
        node_key = class_node.node_id.upper()

        # 确保对应的中心节点存在
        entity_key = class_node.entity_name.upper()
        if entity_key not in self._entities:
            raise ValueError(
                f"类节点 '{class_node.node_id}' 对应的中心节点 '{class_node.entity_name}' 不存在"
            )

        if node_key in self._class_nodes:
            # 如果类节点已存在，更新描述
            existing_node = self._class_nodes[node_key]
            if class_node.description:
                existing_node.description = class_node.description
                existing_node.updated_at = datetime.now()
            return existing_node
        else:
            # 添加新类节点
            logger.debug(f"添加类节点: {class_node.node_id}")
            # 确保类主节点存在
            self._create_or_update_class_master_node(class_node.class_name)
            self._class_nodes[node_key] = class_node
            return class_node

    def get_class_node(self, entity_name: str, class_name: str) -> Optional[ClassNode]:
        """
        获取类节点

        Args:
            entity_name: 实体名称
            class_name: 类名称

        Returns:
            类节点，如果不存在返回None
        """
        node_id = f"{entity_name}:{class_name}"
        return self._class_nodes.get(node_id.upper())

    def get_class_nodes(self, entity_name: Optional[str] = None) -> List[ClassNode]:
        """
        获取类节点列表

        Args:
            entity_name: 如果提供，只返回该实体的类节点

        Returns:
            类节点列表
        """
        if entity_name is None:
            return list(self._class_nodes.values())

        entity_key = entity_name.upper()
        return [
            node
            for node in self._class_nodes.values()
            if node.entity_name.upper() == entity_key
        ]

    def get_class_master_node(self, class_name: str) -> Optional[ClassMasterNode]:
        """获取类主节点（派生自 system；Graph 不维护等价缓存）"""
        class_def = self.system.get_class_definition(class_name)
        if not class_def:
            return None
        return ClassMasterNode(
            class_name=class_def.name, description=class_def.description
        )

    def get_class_master_nodes(self) -> List[ClassMasterNode]:
        """获取所有类主节点列表（派生自 system）"""
        nodes: List[ClassMasterNode] = []
        for class_name_upper in self.system.get_all_classes():
            class_def = self.system.get_class_definition(class_name_upper)
            if not class_def:
                continue
            nodes.append(
                ClassMasterNode(
                    class_name=class_def.name, description=class_def.description
                )
            )
        return nodes

    def get_entity(self, name: str) -> Optional[Entity]:
        """获取实体"""
        return self._entities.get(name.upper())

    def add_relationship(self, relationship: Relationship) -> Relationship:
        """
        添加关系到图中

        关系可以连接到：
        - 中心节点（实体名称，如"小红书"）
        - 类节点（格式为"entity_name:class_name"，如"小红书:购物平台"）

        Args:
            relationship: 要添加的关系

        Returns:
            返回图中的关系（可能是新添加的或已存在的）
        """
        # 检查源节点是否存在（可能是中心节点或类节点）
        source_key = relationship.source.upper()
        source_exists = (
            source_key in self._entities
            or source_key in self._class_nodes
            or self.system.get_class_definition(relationship.source) is not None
        )

        if not source_exists:
            # 检查是否是类节点格式
            if ":" in relationship.source:
                raise ValueError(f"源类节点 '{relationship.source}' 不存在于图中")
            else:
                raise ValueError(f"源节点 '{relationship.source}' 不存在于图中")

        # 检查目标节点是否存在（可能是中心节点或类节点）
        target_key = relationship.target.upper()
        target_exists = (
            target_key in self._entities
            or target_key in self._class_nodes
            or self.system.get_class_definition(relationship.target) is not None
        )

        if not target_exists:
            # 检查是否是类节点格式
            if ":" in relationship.target:
                raise ValueError(f"目标类节点 '{relationship.target}' 不存在于图中")
            else:
                raise ValueError(f"目标节点 '{relationship.target}' 不存在于图中")

        # 检查是否已存在相同的关系（包括 refer 字段）
        for existing_rel in self._relationships:
            # 比较 refer 字段（顺序无关）
            existing_refer_set = set([r.upper() for r in existing_rel.refer])
            new_refer_set = set([r.upper() for r in relationship.refer])

            if (
                existing_rel.source.upper() == source_key
                and existing_rel.target.upper() == target_key
                and existing_rel.description == relationship.description
                and existing_refer_set == new_refer_set  # refer 必须相同
            ):
                # 如果已存在（包括 refer 相同），累加次数
                logger.debug(
                    f"更新已存在的关系次数: {relationship.source} -> {relationship.target} "
                    f"(增加次数: {relationship.count}, 原次数: {existing_rel.count}, refer: {relationship.refer})"
                )
                existing_rel.increment_count(relationship.count)
                return existing_rel

        # 添加新关系
        logger.debug(
            f"添加新关系: {relationship.source} -> {relationship.target} (次数: {relationship.count})"
        )
        self._relationships.add(relationship)

        # 更新节点关系映射（包括实体和类节点）
        self._entity_relationships[source_key].add(target_key)
        self._entity_relationships[target_key].add(source_key)

        return relationship

    def get_relationships(self, node_name: Optional[str] = None) -> List[Relationship]:
        """
        获取关系列表

        Args:
            node_name: 如果提供，只返回与该节点相关的关系（可以是实体名称或类节点ID）

        Returns:
            关系列表
        """
        if node_name is None:
            return list(self._relationships)

        node_key = node_name.upper()
        return [
            rel
            for rel in self._relationships
            if rel.source.upper() == node_key or rel.target.upper() == node_key
        ]

    def get_entities(self) -> List[Entity]:
        """获取所有实体列表"""
        return list(self._entities.values())

    def get_entity_count(self) -> int:
        """获取中心节点数量"""
        return len(self._entities)

    def get_class_node_count(self) -> int:
        """获取类节点数量"""
        return len(self._class_nodes)

    def get_class_master_node_count(self) -> int:
        """获取类主节点数量"""
        # “类本身”的真相只在 system
        return len(self.system.get_all_classes())

    def get_total_node_count(self) -> int:
        """获取总节点数量（中心节点 + 类节点 + 类主节点）"""
        return (
            len(self._entities)
            + len(self._class_nodes)
            + self.get_class_master_node_count()
        )

    def get_relationship_count(self) -> int:
        """获取关系数量"""
        return len(self._relationships)

    def merge(self, other: "Graph") -> None:
        """
        合并另一个图到当前图（用于增量更新）

        Args:
            other: 要合并的图
        """
        logger.debug(
            f"开始合并图: 当前图有 {self.get_entity_count()} 个实体, {self.get_relationship_count()} 个关系"
        )
        logger.debug(
            f"要合并的图有 {other.get_entity_count()} 个实体, {other.get_relationship_count()} 个关系"
        )

        # 合并实体
        merged_entities = 0
        new_entities = 0
        for entity in other.get_entities():
            existing = self.get_entity(entity.name)
            self.add_entity(entity)
            if existing:
                merged_entities += 1
            else:
                new_entities += 1

        logger.debug(f"实体合并完成: 新增 {new_entities} 个, 更新 {merged_entities} 个")

        # 合并关系
        merged_relationships = 0
        skipped_relationships = 0
        for relationship in other.get_relationships():
            try:
                existing = any(
                    rel.source.upper() == relationship.source.upper()
                    and rel.target.upper() == relationship.target.upper()
                    and rel.description == relationship.description
                    for rel in self._relationships
                )
                self.add_relationship(relationship)
                if existing:
                    merged_relationships += 1
            except ValueError:
                # 如果实体不存在，跳过该关系
                skipped_relationships += 1
                logger.debug(
                    f"跳过关系（实体不存在）: {relationship.source} -> {relationship.target}"
                )

        logger.debug(
            f"关系合并完成: 新增 {other.get_relationship_count() - merged_relationships - skipped_relationships} 个, 更新 {merged_relationships} 个, 跳过 {skipped_relationships} 个"
        )
        logger.debug(
            f"合并后: {self.get_entity_count()} 个实体, {self.get_relationship_count()} 个关系"
        )

    def save(self, file_path: Path) -> None:
        """保存图到文件（包括 system 定义信息）"""
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            pickle.dump(
                {
                    "system": self.system.to_dict(),
                    "entities": [e.to_dict() for e in self._entities.values()],
                    "class_nodes": [cn.to_dict() for cn in self._class_nodes.values()],
                    # 向后兼容导出字段：class_master_nodes 派生自 system
                    "class_master_nodes": [
                        cmn.to_dict() for cmn in self.get_class_master_nodes()
                    ],
                    "relationships": [r.to_dict() for r in self._relationships],
                },
                f,
            )

    @classmethod
    def load(cls, file_path: Path) -> "Graph":
        """从文件加载图（包括 system 定义信息）"""
        graph = cls(system=System(), include_predefined_entities=False)
        with open(file_path, "rb") as f:
            data = pickle.load(f)

            # 1) system（新格式）
            if "system" in data and isinstance(data["system"], dict):
                graph.system = System.from_dict(data["system"])
                # 重新订阅（graph.system 被替换）
                graph.system.subscribe_class_added(graph._on_system_class_added)
            else:
                # 兼容旧格式：class_definitions
                class_definitions_dict = data.get("class_definitions", {}) or {}
                if class_definitions_dict:
                    # class_definitions_dict 的 key 可能是大写类名，value 是 ClassDefinition.to_dict()
                    graph.system = System.from_dict({"classes": class_definitions_dict})
                    graph.system.subscribe_class_added(graph._on_system_class_added)
                    logger.debug(
                        f"从旧格式加载了 {len(class_definitions_dict)} 个类定义"
                    )

            # 加载实体
            for entity_data in data.get("entities", []):
                entity = Entity.from_dict(entity_data)
                graph._entities[entity.name.upper()] = entity
                # 为每个类创建类节点
                for class_instance in entity.classes:
                    graph._create_or_update_class_node(
                        entity, class_instance.class_name
                    )

            # 加载类节点（向后兼容，如果文件中有类节点数据）
            for class_node_data in data.get("class_nodes", []):
                class_node = ClassNode.from_dict(class_node_data)
                graph._class_nodes[class_node.node_id.upper()] = class_node
                # 类主节点不再从文件加载：直接由 system 派生

            # 加载关系
            for rel_data in data.get("relationships", []):
                relationship = Relationship.from_dict(rel_data)
                graph._relationships.add(relationship)

                # 更新节点关系映射
                source_key = relationship.source.upper()
                target_key = relationship.target.upper()
                graph._entity_relationships[source_key].add(target_key)
                graph._entity_relationships[target_key].add(source_key)

        return graph

    def to_networkx(self):
        """转换为NetworkX图对象（用于可视化）"""
        try:
            import networkx as nx
        except ImportError:
            raise ImportError("需要安装networkx: pip install networkx")

        G = nx.DiGraph()

        # 添加中心节点
        for entity in self._entities.values():
            G.add_node(
                entity.name,
                node_type="entity",
                classes=[c.class_name for c in entity.classes],
                description=entity.description,
            )

        # 添加类主节点（类本身）
        for master in self.get_class_master_nodes():
            G.add_node(
                master.node_id,
                node_type="class_master",
                class_name=master.class_name,
                description=master.description,
            )

        # 添加类节点
        for class_node in self._class_nodes.values():
            G.add_node(
                class_node.node_id,
                node_type="class_node",
                entity_name=class_node.entity_name,
                class_name=class_node.class_name,
                description=class_node.description,
            )
            # 添加类节点到中心节点的连接
            G.add_edge(
                class_node.node_id,
                class_node.entity_name,
                edge_type="has_class",
                description=f"{class_node.entity_name}拥有{class_node.class_name}类",
            )
            # 添加类节点到类主节点的连接（类节点 = 实体:类，是二者的结合）
            G.add_edge(
                class_node.node_id,
                class_node.class_name,
                edge_type="instance_of_class",
                description=f"{class_node.node_id}属于{class_node.class_name}类",
            )

        # 添加关系边
        for relationship in self._relationships:
            G.add_edge(
                relationship.source,
                relationship.target,
                edge_type="relationship",
                description=relationship.description,
                count=relationship.count,
            )

        return G

    def print_graph(
        self, show_properties: bool = True, show_relationships: bool = True
    ):
        """
        打印图的详细信息

        Args:
            show_properties: 是否显示实体的属性
            show_relationships: 是否显示关系
        """
        print("\n" + "=" * 80)
        print("📊 Graph 数据概览")
        print("=" * 80)

        # 统计信息
        print(f"\n📈 统计信息:")
        print(f"  • 实体数量: {self.get_entity_count()}")
        print(f"  • 类节点数量: {self.get_class_node_count()}")
        print(f"  • 类定义数量: {self.get_class_master_node_count()}")
        print(f"  • 关系数量: {self.get_relationship_count()}")
        print(f"  • 总节点数: {self.get_total_node_count()}")

        # 类定义
        print(f"\n📚 类定义 ({self.get_class_master_node_count()} 个):")
        for class_name in sorted(self.system.get_all_classes()):
            class_def = self.system.get_class_definition(class_name)
            if class_def:
                print(f"  • {class_def.name}")
                print(f"    描述: {class_def.description}")
                if class_def.properties:
                    print(
                        f"    属性: {', '.join([p.name for p in class_def.properties])}"
                    )

        # 实体
        print(f"\n👥 实体 ({self.get_entity_count()} 个):")
        for entity in sorted(self.get_entities(), key=lambda e: e.name):
            classes = [c.class_name for c in entity.classes]
            print(f"\n  🔹 {entity.name}")
            print(f"    描述: {entity.description}")
            print(f"    类别: {', '.join(classes)}")

            if show_properties:
                for class_instance in entity.classes:
                    props = class_instance.properties
                    if props:
                        print(f"    [{class_instance.class_name}] 属性:")
                        for prop_name, prop_value in props.items():
                            value = prop_value.value if prop_value.value else "(未设置)"
                            print(f"      - {prop_name}: {value}")

        # 关系
        if show_relationships and self.get_relationship_count() > 0:
            print(f"\n🔗 关系 ({self.get_relationship_count()} 个):")
            for rel in sorted(
                self.get_relationships(),
                key=lambda r: (r.source, r.target),
            ):
                count_str = f" (x{rel.count})" if rel.count > 1 else ""
                print(f"  • {rel.source} → {rel.target}{count_str}")
                print(f"    {rel.description}")

        print("\n" + "=" * 80)
