"""
测试关系count属性累加逻辑

这个测试验证在merge阶段，相同的关系是否能正确累加count。
"""

from src.models.entity import System, Entity
from src.models.graph import Graph
from src.models.relationship import Relationship
from src.combiners.combiner import Combiner


def test_relationship_count_accumulation():
    """测试关系count累加"""

    print("\n" + "=" * 60)
    print("测试关系count累加逻辑")
    print("=" * 60)

    # 创建System和Graph
    system = System()
    graph = Graph(system=system, include_predefined_entities=False)

    # 添加测试实体
    entity1 = Entity(name="用户", description="用户实体")
    entity2 = Entity(name="微信", description="微信应用")

    graph.add_entity(entity1)
    graph.add_entity(entity2)

    print(f"\n初始状态: {graph.get_relationship_count()} 个关系")

    # 测试场景1: 添加第一个关系（count=1）
    print("\n场景1: 添加第一个关系 (count=1)")
    rel1 = Relationship(
        source="用户", target="微信", description="打开应用", count=1, refer=[]
    )
    graph.add_relationship(rel1)
    print(f"添加后: {graph.get_relationship_count()} 个关系")

    # 检查关系count
    rels = graph.get_relationships()
    if rels:
        print(f"关系count: {rels[0].count}")

    # 测试场景2: 添加相同的关系（count=1），应该累加到2
    print("\n场景2: 添加相同的关系 (count=1)，应该累加")
    rel2 = Relationship(
        source="用户", target="微信", description="打开应用", count=1, refer=[]
    )
    result = graph.add_relationship(rel2)
    print(f"添加后: {graph.get_relationship_count()} 个关系")
    print(f"关系count: {result.count} (期望: 2)")

    assert graph.get_relationship_count() == 1, "应该只有1个关系"
    assert result.count == 2, f"count应该是2，实际是{result.count}"

    # 测试场景3: 添加相同关系但count=3，应该累加到5
    print("\n场景3: 添加相同的关系 (count=3)，应该累加到5")
    rel3 = Relationship(
        source="用户", target="微信", description="打开应用", count=3, refer=[]
    )
    result = graph.add_relationship(rel3)
    print(f"添加后: {graph.get_relationship_count()} 个关系")
    print(f"关系count: {result.count} (期望: 5)")

    assert graph.get_relationship_count() == 1, "应该只有1个关系"
    assert result.count == 5, f"count应该是5，实际是{result.count}"

    # 测试场景4: 添加不同refer的相同关系，应该创建新关系
    print("\n场景4: 添加不同refer的相同关系，应该创建新关系")
    rel4 = Relationship(
        source="用户", target="微信", description="打开应用", count=1, refer=["手机"]
    )
    result = graph.add_relationship(rel4)
    print(f"添加后: {graph.get_relationship_count()} 个关系 (期望: 2)")
    print(f"新关系count: {result.count} (期望: 1)")

    assert graph.get_relationship_count() == 2, "应该有2个关系"
    assert result.count == 1, f"新关系count应该是1，实际是{result.count}"

    # 测试场景5: 使用Combiner批量添加关系
    print("\n场景5: 使用Combiner批量添加相同关系")
    combiner = Combiner(graph, strict_validation=False)

    # 添加多个相同的关系
    rels_to_add = [
        Relationship(
            source="用户", target="微信", description="打开应用", count=1, refer=[]
        ),
        Relationship(
            source="用户", target="微信", description="打开应用", count=2, refer=[]
        ),
    ]

    stats = combiner.combine_relationships(rels_to_add)
    print(f"Combiner统计: 新增 {stats['added']} 个, 更新 {stats['updated']} 个")
    print(f"最终: {graph.get_relationship_count()} 个关系")

    # 检查最终count
    rels = graph.get_relationships()
    for rel in rels:
        if rel.source == "用户" and rel.target == "微信" and not rel.refer:
            print(f"最终count: {rel.count} (期望: 8, 因为 5+1+2=8)")
            assert rel.count == 8, f"count应该是8，实际是{rel.count}"

    print("\n" + "=" * 60)
    print("所有测试通过！count累加逻辑正常工作")
    print("=" * 60)


if __name__ == "__main__":
    test_relationship_count_accumulation()
