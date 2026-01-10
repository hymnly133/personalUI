"""
日志配置模块
根据 SIMPLERAG_VERBOSE 环境变量控制日志详细程度
"""

import logging
import os
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler

# 需要屏蔽的第三方库logger列表
THIRD_PARTY_LOGGERS = [
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpx",
    "openai",
    "openai._base_client",
    "openai._client",
    "urllib3",
    "urllib3.connectionpool",
]


def _get_log_dir() -> Path:
    """
    获取日志文件目录

    Returns:
        日志目录路径
    """
    # 尝试获取 graph_service.py 所在的目录（backend目录）
    # 如果无法确定，则使用当前工作目录
    try:
        import sys
        import inspect

        # 方法1: 查找 graph_service 模块
        if "graph_service" in sys.modules:
            graph_service_module = sys.modules["graph_service"]
            if (
                hasattr(graph_service_module, "__file__")
                and graph_service_module.__file__
            ):
                file_path = Path(graph_service_module.__file__)
                log_dir = file_path.parent / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                return log_dir

        # 方法2: 通过调用栈查找 backend 目录
        frame = inspect.currentframe()
        if frame:
            # 向上查找调用栈，寻找包含 'backend' 的路径
            current_frame = frame.f_back
            while current_frame:
                filename = current_frame.f_code.co_filename
                if "backend" in filename:
                    file_path = Path(filename).parent
                    log_dir = file_path / "logs"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    return log_dir
                current_frame = current_frame.f_back
    except Exception:
        pass

    # 方法3: 尝试查找 graphrag/backend 目录
    try:
        current = Path.cwd()
        # 向上查找 graphrag 目录
        for parent in [current] + list(current.parents):
            backend_dir = parent / "graphrag" / "backend"
            if backend_dir.exists():
                log_dir = backend_dir / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                return log_dir
    except Exception:
        pass

    # 默认使用当前工作目录下的 logs 目录
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(
    verbose: Optional[bool] = None, log_file: Optional[str] = None
) -> None:
    """
    设置日志配置

    Args:
        verbose: 是否启用详细日志，如果为None则从环境变量读取
        log_file: 日志文件名，如果为None则使用默认名称 "graph_service.log"
    """
    # 确定是否启用详细日志
    if verbose is None:
        verbose_env = os.environ.get("SIMPLERAG_VERBOSE", "").lower()
        verbose = verbose_env in ("1", "true", "yes", "on")

    # 设置日志级别
    if verbose:
        level = logging.DEBUG
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    else:
        level = logging.INFO
        format_str = "%(asctime)s - %(levelname)s - %(message)s"

    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除现有的处理器（避免重复添加）
    root_logger.handlers.clear()

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(format_str, datefmt="%Y-%m-%d %H:%M:%S")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 创建文件处理器
    if log_file is None:
        log_file = "graph_service.log"

    log_dir = _get_log_dir()
    log_path = log_dir / log_file

    # 使用 RotatingFileHandler 进行日志轮转
    # maxBytes: 10MB, backupCount: 保留5个备份文件
    file_handler = RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"  # 10MB
    )
    file_handler.setLevel(level)

    # 文件日志使用更详细的格式
    file_format_str = (
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    file_formatter = logging.Formatter(file_format_str, datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 屏蔽第三方库的日志输出（设置为WARNING级别，只显示警告和错误）
    for logger_name in THIRD_PARTY_LOGGERS:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.setLevel(logging.WARNING)
        # 防止日志传播到父logger
        third_party_logger.propagate = False


# 标记是否已经初始化过日志
_logging_initialized = False


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志记录器

    Args:
        name: 日志记录器名称（通常是模块名）

    Returns:
        配置好的日志记录器
    """
    global _logging_initialized

    # 如果还没有初始化，则自动初始化（包括文件日志）
    if not _logging_initialized:
        setup_logging()
        _logging_initialized = True

    return logging.getLogger(name)
