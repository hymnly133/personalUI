"""
测试数据库持久化功能

用法:
    python test_database_persistence.py
"""

import asyncio
import sys
from pathlib import Path

# 添加路径
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent / "simple_graphrag"))

from graph_service import graph_service
from dotenv import load_dotenv

load_dotenv()


async def test_save_and_load():
    """测试保存和加载功能"""
    print("=" * 60)
    print("测试数据库持久化功能")
    print("=" * 60)

    # 1. 初始化服务
    print("\n1. 初始化 GraphService...")
    await graph_service.initialize()
    print("✓ 服务初始化完成")

    # 2. 提交测试任务
    print("\n2. 提交测试任务...")
    test_text = """
    小红书是一个生活方式分享平台，成立于2013年。
    它允许用户分享购物心得和生活经验。
    """
    task_id = await graph_service.submit_task(test_text)
    print(f"✓ 任务已提交: {task_id[:8]}...")

    # 3. 等待任务完成
    print("\n3. 等待任务完成...")
    while True:
        status = graph_service.get_task_status(task_id)
        if status and status["status"] in ["completed", "failed", "cancelled"]:
            print(f"✓ 任务状态: {status['status']}")
            break
        await asyncio.sleep(1)

    # 4. 查看当前统计信息
    print("\n4. 当前图谱统计信息:")
    stats = graph_service.get_stats()
    print(f"   - 类定义: {stats['system']['classes']}")
    print(f"   - 实体: {stats['graph']['entities']}")
    print(f"   - 关系: {stats['graph']['relationships']}")

    # 5. 保存数据库
    print("\n5. 保存数据库...")
    save_result = await graph_service.save_database()
    print(f"✓ {save_result['message']}")
    print(f"   - 文件路径: {save_result['file_path']}")
    print(f"   - 文件大小: {save_result['file_size']} 字节")

    # 6. 列出数据库文件
    print("\n6. 列出所有数据库文件:")
    databases = await graph_service.list_database_files()
    for db in databases:
        default_mark = "✓" if db["is_default"] else " "
        print(f"   [{default_mark}] {db['file_name']} " f"({db['file_size']} 字节)")

    # 7. 测试加载
    print("\n7. 测试加载数据库...")
    load_result = await graph_service.load_database()
    print(f"✓ {load_result['message']}")

    # 8. 验证加载后的数据
    print("\n8. 验证加载后的图谱:")
    stats_after = graph_service.get_stats()
    print(f"   - 类定义: {stats_after['system']['classes']}")
    print(f"   - 实体: {stats_after['graph']['entities']}")
    print(f"   - 关系: {stats_after['graph']['relationships']}")

    # 9. 测试自动保存配置
    print("\n9. 测试自动保存配置...")
    graph_service.set_auto_save(False)
    print("✓ 自动保存已禁用")

    graph_service.set_auto_save(True)
    print("✓ 自动保存已启用")

    # 10. 查看数据库状态
    print("\n10. 数据库状态:")
    status_result = {
        "initialized": graph_service.sg is not None,
        "default_path": str(graph_service.get_default_database_path()),
        "auto_save_enabled": graph_service.auto_save_enabled,
        "data_directory": str(graph_service.data_dir),
    }
    print(f"   - 已初始化: {status_result['initialized']}")
    print(f"   - 默认路径: {status_result['default_path']}")
    print(f"   - 自动保存: {status_result['auto_save_enabled']}")
    print(f"   - 数据目录: {status_result['data_directory']}")

    # 11. 关闭服务
    print("\n11. 关闭服务...")
    await graph_service.shutdown()
    print("✓ 服务已关闭（自动保存已触发）")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


async def test_custom_save_path():
    """测试自定义保存路径"""
    print("\n" + "=" * 60)
    print("测试自定义保存路径")
    print("=" * 60)

    # 初始化
    await graph_service.initialize()

    # 自定义路径
    custom_path = graph_service.data_dir / "test_backup.pkl"
    print(f"\n保存到自定义路径: {custom_path}")

    result = await graph_service.save_database(custom_path)
    print(f"✓ {result['message']}")

    # 验证文件存在
    if custom_path.exists():
        print(f"✓ 文件已创建: {custom_path.stat().st_size} 字节")
    else:
        print("✗ 文件未创建")

    await graph_service.shutdown()


async def main():
    """主函数"""
    try:
        # 测试基本功能
        await test_save_and_load()

        # 测试自定义路径
        # await test_custom_save_path()

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # 确保服务关闭
        try:
            if graph_service.sg:
                await graph_service.shutdown()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())
