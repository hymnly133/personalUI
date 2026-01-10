"""
关系数据模型
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class Relationship:
    """关系类，表示知识图谱中的边"""

    source: str  # 源节点（可以是实体节点、类节点或类主节点）
    target: str  # 目标节点（可以是实体节点、类节点或类主节点）
    description: str  # 关系描述
    count: int  # 关系出现次数 (>= 1)
    refer: List[str] = field(
        default_factory=list
    )  # 参与此关系的其他实体或实体类（引用）
    semantic_times: List[str] = field(
        default_factory=list
    )  # 语义时间列表（记录关系所表示事件的发生时间，ISO 8601格式）
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

        # 确保关系次数至少为1
        self.count = max(1, self.count)

    def __hash__(self) -> int:
        """用于去重和集合操作"""
        # 将 refer 列表排序后转为元组，保证顺序无关的哈希一致性
        refer_tuple = tuple(sorted([r.upper() for r in self.refer]))
        return hash(
            (
                self.source.upper(),
                self.target.upper(),
                self.description,
                refer_tuple,
            )
        )

    def __eq__(self, other) -> bool:
        """关系相等性判断"""
        if not isinstance(other, Relationship):
            return False
        # 比较时不考虑 refer 的顺序
        self_refer = set([r.upper() for r in self.refer])
        other_refer = set([r.upper() for r in other.refer])
        return (
            self.source.upper() == other.source.upper()
            and self.target.upper() == other.target.upper()
            and self.description == other.description
            and self_refer == other_refer
        )

    def increment_count(
        self, additional_count: int = 1, semantic_time: Optional[str] = None
    ) -> None:
        """
        增加关系次数（用于增量更新时合并关系）

        Args:
            additional_count: 要增加的次数
            semantic_time: 可选的语义时间（ISO 8601格式），如果提供则追加到semantic_times列表
        """
        self.count = max(1, self.count + additional_count)
        self.updated_at = datetime.now()
        if semantic_time:
            self.semantic_times.append(semantic_time)

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "source": self.source,
            "target": self.target,
            "description": self.description,
            "count": self.count,
            "refer": self.refer,  # 引用列表
            "semantic_times": self.semantic_times,  # 语义时间列表
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Relationship":
        """从字典创建关系"""
        created_at = None
        updated_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(data["updated_at"])

        # 向后兼容：如果数据中有 strength 但没有 count，使用 strength
        count = data.get("count", data.get("strength", 1))

        # 向后兼容：如果数据中没有 refer，使用空列表
        refer = data.get("refer", [])

        # 向后兼容：如果数据中没有 semantic_times，使用空列表
        semantic_times = data.get("semantic_times", [])

        # 向后兼容：支持旧字段名 source/target
        source = data.get("source") or data.get("source")
        target = data.get("target") or data.get("target")

        return cls(
            source=source,
            target=target,
            description=data["description"],
            count=count,
            refer=refer,
            semantic_times=semantic_times,
            created_at=created_at,
            updated_at=updated_at,
        )
