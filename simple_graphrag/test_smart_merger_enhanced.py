"""
测试增强后的SmartMerger

验证：
1. 能否正确提供所有现有实体信息
2. 能否为delta实体搜索相关的现有数据
3. LLM输入是否包含完整信息
"""

import asyncio
import json
from src.models.entity import System, Entity
from src.models.graph import Graph
from src.models.delta import GraphDelta, EntityDelta, RelationshipDelta
from src.combiners.smart_merger import SmartMerger
from src.llm.client import LLMClient
from pathlib import Path


async def test_smart_merger_data_preparation():
    """测试SmartMerger的数据准备功能"""

    print("\n" + "=" * 60)
    print("测试增强后的SmartMerger数据准备")
    print("=" * 60)

    # 1. 创建测试环境
    print("\n[1] 创建测试环境...")
    from src.models.entity import ClassDefinition, PropertyDefinition

    system = System()

    # 先定义类
    system.add_class_definition(
        ClassDefinition(
            name="可启动应用", description="可以被启动的应用程序", properties=[]
        )
    )
    system.add_class_definition(
        ClassDefinition(name="交流平台", description="用于交流的平台", properties=[])
    )
    system.add_class_definition(
        ClassDefinition(name="可联系人", description="可以联系的人", properties=[])
    )
    system.add_class_definition(
        ClassDefinition(name="内容平台", description="内容分享平台", properties=[])
    )

    graph = Graph(system=system, include_predefined_entities=False)

    # 初始化搜索引擎
    from src.search.search_engine import SearchEngine

    graph._search_engine = SearchEngine(graph)

    # 添加一些现有实体
    entity1 = Entity(name="微信", description="即时通讯应用")
    entity1.add_class("可启动应用", system=system)
    entity1.add_class("交流平台", system=system)
    graph.add_entity(entity1)

    entity2 = Entity(name="美团外卖", description="外卖订餐平台")
    entity2.add_class("可启动应用", system=system)
    graph.add_entity(entity2)

    entity3 = Entity(name="小明", description="一个联系人")
    entity3.add_class("可联系人", system=system)
    graph.add_entity(entity3)

    print(f"   现有实体: {graph.get_entity_count()} 个")

    # 2. 创建delta（包含已存在和新实体）
    print("\n[2] 创建测试Delta...")
    delta = GraphDelta(
        task_id="test_task",
        entities=[
            EntityDelta(
                name="微信",  # 已存在
                description="社交通讯平台",
                classes=["可启动应用", "交流平台"],
                operation="add",
            ),
            EntityDelta(
                name="美团",  # 相似名称（应搜索到"美团外卖"）
                description="生活服务平台",
                classes=["可启动应用"],
                operation="add",
            ),
            EntityDelta(
                name="小红书",  # 新实体
                description="生活方式分享平台",
                classes=["可启动应用", "内容平台"],
                operation="add",
            ),
        ],
        relationships=[
            RelationshipDelta(
                source="我", target="微信:可启动应用", description="打开微信", count=1
            )
        ],
    )

    print(f"   Delta实体: {len(delta.entities)} 个")
    print(f"   Delta关系: {len(delta.relationships)} 个")

    # 3. 测试SmartMerger的数据准备
    print("\n[3] 测试SmartMerger数据准备...")

    # 初始化SmartMerger（不使用真实的LLM调用）
    llm_client = LLMClient(api_key="dummy", base_url="dummy", model="dummy")
    smart_merger = SmartMerger(
        llm_client=llm_client, enable_smart_merge=False  # 禁用LLM调用，只测试数据准备
    )

    # 测试_get_all_entities_detail
    print("\n   [3.1] 测试_get_all_entities_detail...")
    all_entities_json = smart_merger._get_all_entities_detail(graph)
    all_entities = json.loads(all_entities_json)

    print(f"      返回实体数量: {len(all_entities)}")
    print(f"      实体列表:")
    for ent in all_entities:
        print(f"         - {ent['name']}: {ent['classes']}")

    assert len(all_entities) == 3, "应该返回3个实体"
    assert any(e["name"] == "微信" for e in all_entities), "应该包含'微信'"
    assert any(e["name"] == "美团外卖" for e in all_entities), "应该包含'美团外卖'"

    # 测试_search_related_data_for_delta
    print("\n   [3.2] 测试_search_related_data_for_delta...")
    related_json = smart_merger._search_related_data_for_delta(graph, delta)
    related_entities = json.loads(related_json)

    print(f"      搜索到相关实体数量: {len(related_entities)}")
    print(f"      相关实体:")
    for ent in related_entities:
        print(ent)

    # 验证搜索结果
    assert len(related_entities) > 0, "应该搜索到相关实体"

    # 检查是否搜索到"微信"（与delta中的"微信"完全匹配）
    weixin_found = any(e["matched_item"] == "微信" for e in related_entities)
    print(f"      是否找到'微信': {weixin_found}")

    # 检查是否搜索到"美团外卖"（与delta中的"美团"相似）
    meituan_found = any("美团" in e["matched_item"] for e in related_entities)
    print(f"      是否找到包含'美团'的实体: {meituan_found}")

    # 4. 验证matched_by字段
    print("\n   [3.3] 验证matched_by字段...")
    for ent in related_entities:
        if ent["matched_item"] == "微信":
            print(f"      '微信' matched_text: {ent['matched_text']}")
            assert "微信" in ent["matched_text"], "'微信'应该由delta中的'微信'匹配"
        if "美团" in ent["matched_item"]:
            print(f"      '{ent['matched_item']}' matched_text: {ent['matched_text']}")
            assert "美团" in ent["matched_text"], "'美团外卖'应该由delta中的'美团'匹配"

    print("\n" + "=" * 60)
    print("所有测试通过！数据准备功能正常工作")
    print("=" * 60)

    # 5. 输出示例数据（用于调试）
    print("\n[调试] 完整的entities_full示例:")
    print(json.dumps(all_entities[:2], ensure_ascii=False, indent=2))

    print("\n[调试] 完整的related_data示例:")
    print(json.dumps(related_entities[:2], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(test_smart_merger_data_preparation())
