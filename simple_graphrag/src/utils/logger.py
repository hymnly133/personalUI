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
    
    配置说明：
    - 控制台：始终输出INFO级别日志
    - 文件1 (debug)：输出DEBUG级别及以上的所有日志
    - 文件2 (info)：输出INFO级别及以上的日志

    Args:
        verbose: 是否启用详细日志，如果为None则从环境变量读取（用于控制DEBUG文件日志）
        log_file: 日志文件名前缀，如果为None则使用默认名称 "graph_service"
    """
    # 确定是否启用详细日志（用于DEBUG文件）
    if verbose is None:
        verbose_env = os.environ.get("SIMPLERAG_VERBOSE", "").lower()
        verbose = verbose_env in ("1", "true", "yes", "on")

    # 获取根日志记录器，设置为DEBUG级别以捕获所有日志
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 清除现有的处理器（避免重复添加）
    root_logger.handlers.clear()

    # ========== 1. 创建控制台处理器 (INFO级别) ==========
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # 控制台固定为INFO级别
    console_format_str = "%(asctime)s - %(levelname)s - %(message)s"
    console_formatter = logging.Formatter(console_format_str, datefmt="%Y-%m-%d %H:%M:%S")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 获取日志目录
    log_dir = _get_log_dir()
    
    # 确定日志文件名前缀
    if log_file is None:
        log_file = "graph_service"

    # ========== 2. 创建DEBUG级别文件处理器 ==========
    debug_log_path = log_dir / f"{log_file}_debug.log"
    debug_file_handler = RotatingFileHandler(
        debug_log_path, 
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5, 
        encoding="utf-8"
    )
    debug_file_handler.setLevel(logging.DEBUG)  # DEBUG及以上级别
    
    # DEBUG文件使用详细格式
    debug_format_str = (
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    debug_formatter = logging.Formatter(debug_format_str, datefmt="%Y-%m-%d %H:%M:%S")
    debug_file_handler.setFormatter(debug_formatter)
    root_logger.addHandler(debug_file_handler)

    # ========== 3. 创建INFO级别文件处理器 ==========
    info_log_path = log_dir / f"{log_file}_info.log"
    info_file_handler = RotatingFileHandler(
        info_log_path, 
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5, 
        encoding="utf-8"
    )
    info_file_handler.setLevel(logging.INFO)  # INFO及以上级别
    
    # INFO文件使用标准格式
    info_format_str = (
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    info_formatter = logging.Formatter(info_format_str, datefmt="%Y-%m-%d %H:%M:%S")
    info_file_handler.setFormatter(info_formatter)
    root_logger.addHandler(info_file_handler)

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
