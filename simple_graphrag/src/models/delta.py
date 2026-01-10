"""
增量更新数据包格式

定义用于任务间增量更新的数据结构，支持类、属性、实体、关系的增量操作。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime


@dataclass
class PropertyDelta:
    """
    属性增量更新

    Attributes:
        name: 属性名称
        description: 属性描述
        required: 是否为必选属性
        value_required: 属性值是否必填
        operation: 操作类型 ("add", "update", "remove")
    """

    name: str
    description: Optional[str] = None
    required: Optional[bool] = None
    value_required: Optional[bool] = None
    operation: str = "add"  # "add", "update", "remove"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "value_required": self.value_required,
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PropertyDelta":
        """从字典创建属性增量"""
        return cls(
            name=data["name"],
            description=data.get("description"),
            required=data.get("required"),
            value_required=data.get("value_required"),
            operation=data.get("operation", "add"),
        )


@dataclass
class ClassDelta:
    """
    类增量更新

    Attributes:
        name: 类名称
        description: 类描述
        properties: 属性增量列表
        operation: 操作类型 ("add", "update")
    """

    name: str
    description: Optional[str] = None
    properties: List[PropertyDelta] = field(default_factory=list)
    operation: str = "add"  # "add", "update"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "properties": [prop.to_dict() for prop in self.properties],
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClassDelta":
        """从字典创建类增量"""
        return cls(
            name=data["name"],
            description=data.get("description"),
            properties=[
                PropertyDelta.from_dict(prop_data)
                for prop_data in data.get("properties", [])
            ],
            operation=data.get("operation", "add"),
        )


@dataclass
class EntityDelta:
    """
    实体增量更新

    Attributes:
        name: 实体名称
        description: 实体描述
        classes: 类名列表
        properties: 属性值字典 {class_name: {property_name: value}}
        operation: 操作类型 ("add", "update", "merge")
    """

    name: str
    description: Optional[str] = None
    classes: List[str] = field(default_factory=list)
    properties: Dict[str, Dict[str, str]] = field(default_factory=dict)
    operation: str = "add"  # "add", "update", "merge"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "classes": self.classes,
            "properties": self.properties,
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EntityDelta":
        """从字典创建实体增量"""
        return cls(
            name=data["name"],
            description=data.get("description"),
            classes=data.get("classes", []),
            properties=data.get("properties", {}),
            operation=data.get("operation", "add"),
        )


@dataclass
class RelationshipDelta:
    """
    关系增量更新

    Attributes:
        source: 源节点（可以是实体节点、类节点或类主节点）
        target: 目标节点（可以是实体节点、类节点或类主节点）
        description: 关系描述
        count: 关系强度/次数
        refer: 参与此关系的其他实体或实体类（引用列表）
        semantic_times: 语义时间列表（记录关系所表示事件的发生时间，ISO 8601格式）
        operation: 操作类型 ("add", "update", "merge", "increment_count")
        increment_amount: 【仅用于increment_count操作】要增加的次数
    """

    source: str
    target: str
    description: str
    count: int = 1
    refer: List[str] = field(default_factory=list)  # 引用列表
    semantic_times: List[str] = field(default_factory=list)  # 语义时间列表
    operation: str = "add"  # "add", "update", "merge", "increment_count"
    increment_amount: int = 0  # 仅用于increment_count操作

    def to_dict(self) -> dict:
        """转换为字典格式"""
        result = {
            "source": self.source,
            "target": self.target,
            "description": self.description,
            "count": self.count,
            "refer": self.refer,  # 引用列表
            "semantic_times": self.semantic_times,  # 语义时间列表
            "operation": self.operation,
        }
        # 只在increment_count操作时包含increment_amount
        if self.operation == "increment_count":
            result["increment_amount"] = self.increment_amount
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "RelationshipDelta":
        """从字典创建关系增量"""
        # 向后兼容：支持旧字段名 source/target
        source = data.get("source") or data.get("source")
        target = data.get("target") or data.get("target")

        return cls(
            source=source,
            target=target,
            description=data["description"],
            count=data.get("count", 1),
            refer=data.get("refer", []),  # 向后兼容
            semantic_times=data.get("semantic_times", []),  # 向后兼容
            operation=data.get("operation", "add"),
            increment_amount=data.get("increment_amount", 0),
        )


@dataclass
class GraphDelta:
    """
    完整图增量更新包

    Attributes:
        task_id: 任务ID
        classes: 类增量列表
        entities: 实体增量列表
        relationships: 关系增量列表
        metadata: 任务元信息
        created_at: 创建时间
    """

    task_id: str
    classes: List[ClassDelta] = field(default_factory=list)
    entities: List[EntityDelta] = field(default_factory=list)
    relationships: List[RelationshipDelta] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "classes": [cls.to_dict() for cls in self.classes],
            "entities": [ent.to_dict() for ent in self.entities],
            "relationships": [rel.to_dict() for rel in self.relationships],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphDelta":
        """从字典创建图增量"""
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            task_id=data["task_id"],
            classes=[ClassDelta.from_dict(c) for c in data.get("classes", [])],
            entities=[EntityDelta.from_dict(e) for e in data.get("entities", [])],
            relationships=[
                RelationshipDelta.from_dict(r) for r in data.get("relationships", [])
            ],
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )

    def is_empty(self) -> bool:
        """判断增量包是否为空"""
        return not (self.classes or self.entities or self.relationships)

    def get_summary(self) -> str:
        """获取增量包摘要"""
        return (
            f"GraphDelta(task_id={self.task_id}, "
            f"{len(self.classes)} classes, "
            f"{len(self.entities)} entities, "
            f"{len(self.relationships)} relationships)"
        )
