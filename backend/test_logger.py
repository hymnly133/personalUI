"""
测试日志配置脚本
验证是否正确生成两个日志文件（debug和info级别）
"""

import sys
from pathlib import Path

# 将 simple_graphrag 添加到 python 路径
sys.path.append(str(Path(__file__).parent.parent / "simple_graphrag"))

from src.utils.logger import get_logger

# 获取logger
logger = get_logger(__name__)


def test_logging():
    """测试不同级别的日志输出"""

    print("\n" + "=" * 60)
    print("开始测试日志配置...")
    print("=" * 60 + "\n")

    # 输出不同级别的日志
    logger.debug("这是一条 DEBUG 级别的日志 - 应该只出现在 debug 文件中")
    logger.info("这是一条 INFO 级别的日志 - 应该出现在控制台、info文件和debug文件中")
    logger.warning(
        "这是一条 WARNING 级别的日志 - 应该出现在控制台、info文件和debug文件中"
    )
    logger.error("这是一条 ERROR 级别的日志 - 应该出现在控制台、info文件和debug文件中")

    print("\n" + "=" * 60)
    print("日志测试完成！")
    print("=" * 60)
    print("\n预期结果：")
    print("1. 控制台：显示 INFO、WARNING、ERROR（不显示DEBUG）")
    print("2. graph_service_debug.log：显示所有级别（DEBUG、INFO、WARNING、ERROR）")
    print("3. graph_service_info.log：显示 INFO、WARNING、ERROR（不显示DEBUG）")
    print("\n日志文件位置：graphrag/backend/logs/")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    test_logging()
