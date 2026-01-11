# 数据库持久化功能文档

## 概述

本文档介绍 GraphRAG 系统的数据库持久化功能，包括保存、加载和自动保存机制。

## 功能特性

### 1. 数据保存
- 将知识图谱（Graph）保存到本地文件
- 包含所有实体、关系、类定义和系统配置
- 使用 pickle 格式进行序列化
- 支持自定义保存路径

### 2. 数据加载
- 从本地文件恢复完整的知识图谱
- 自动恢复系统配置和状态
- 支持从任意备份文件加载

### 3. 自动保存
- 任务完成后自动保存数据库
- 可配置开启/关闭
- 服务关闭前自动保存

### 4. 数据管理
- 列出所有可用的数据库文件
- 查看数据库状态和统计信息
- 管理多个数据库快照

## 目录结构

```
graphrag/
├── backend/
│   ├── data/                           # 数据存储目录（新增）
│   │   └── graph_database.pkl         # 默认数据库文件
│   ├── graph_service.py                # 后端服务（已更新）
│   ├── main.py                         # API 端点（已更新）
│   └── DATABASE_PERSISTENCE.md         # 本文档
└── simple_graphrag/
    ├── simplegraph.py                  # 核心类（已更新）
    └── src/
        └── models/
            └── graph.py                # Graph 模型（已有 save/load）
```

## API 端点

### 1. 保存数据库

**POST** `/api/database/save`

保存当前知识图谱到文件。

**请求体：**
```json
{
  "file_name": "graph_database.pkl"  // 可选，不指定则使用默认文件名
}
```

**响应：**
```json
{
  "success": true,
  "file_path": "d:\\...\\graphrag\\backend\\data\\graph_database.pkl",
  "file_size": 123456,
  "statistics": {
    "system": {
      "classes": 5,
      "predefined_entities": 2
    },
    "graph": {
      "entities": 10,
      "relationships": 15
    },
    "tasks": {
      "total": 3,
      "by_status": {...}
    }
  },
  "message": "数据库已保存到 ..."
}
```

### 2. 加载数据库

**POST** `/api/database/load`

从文件加载知识图谱。

**请求体：**
```json
{
  "file_name": "graph_database.pkl"  // 可选，不指定则使用默认文件名
}
```

**响应：**
```json
{
  "success": true,
  "file_path": "d:\\...\\graphrag\\backend\\data\\graph_database.pkl",
  "file_size": 123456,
  "statistics": {...},
  "message": "数据库已从 ... 加载"
}
```

### 3. 列出数据库文件

**GET** `/api/database/list`

获取所有可用的数据库文件列表。

**响应：**
```json
[
  {
    "file_name": "graph_database.pkl",
    "file_path": "d:\\...\\graphrag\\backend\\data\\graph_database.pkl",
    "file_size": 123456,
    "modified_time": 1704844800.0,
    "is_default": true
  },
  {
    "file_name": "backup_20240109.pkl",
    "file_path": "d:\\...\\graphrag\\backend\\data\\backup_20240109.pkl",
    "file_size": 120000,
    "modified_time": 1704758400.0,
    "is_default": false
  }
]
```

### 4. 配置自动保存

**PUT** `/api/database/auto-save`

开启或关闭自动保存功能。

**请求体：**
```json
{
  "enabled": true  // true=启用, false=禁用
}
```

**响应：**
```json
{
  "success": true,
  "auto_save_enabled": true,
  "message": "自动保存已启用"
}
```

### 5. 查询数据库状态

**GET** `/api/database/status`

获取当前数据库状态信息。

**响应：**
```json
{
  "initialized": true,
  "default_path": "d:\\...\\graphrag\\backend\\data\\graph_database.pkl",
  "auto_save_enabled": true,
  "data_directory": "d:\\...\\graphrag\\backend\\data",
  "statistics": {
    "system": {...},
    "graph": {...},
    "tasks": {...}
  }
}
```

## 核心类方法

### SimpleGraph 类

#### save(path: Path)
保存图谱到指定路径。

```python
sg = SimpleGraph(config_path=config_path)
sg.save(Path("./data/my_graph.pkl"))
```

#### load(config_path: Path, graph_path: Path, **kwargs)
从文件加载图谱并创建 SimpleGraph 实例。

```python
sg = SimpleGraph.load(
    config_path=Path("./config/config.yaml"),
    graph_path=Path("./data/my_graph.pkl"),
    max_concurrent_tasks=3,
    enable_smart_merge=True
)
```

### GraphService 类

#### save_database(file_path: Optional[Path] = None)
保存数据库（异步方法）。

```python
result = await graph_service.save_database()
# 或指定路径
result = await graph_service.save_database(Path("./data/backup.pkl"))
```

#### load_database(file_path: Optional[Path] = None)
加载数据库（异步方法）。

```python
result = await graph_service.load_database()
# 或指定路径
result = await graph_service.load_database(Path("./data/backup.pkl"))
```

#### list_database_files()
列出所有数据库文件（异步方法）。

```python
databases = await graph_service.list_database_files()
```

#### set_auto_save(enabled: bool)
设置自动保存开关。

```python
graph_service.set_auto_save(True)  # 启用
graph_service.set_auto_save(False)  # 禁用
```

## 使用场景

### 场景 1: 定期备份

```python
import asyncio
from pathlib import Path
from datetime import datetime

async def backup_database():
    # 生成带时间戳的文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(f"./data/backup_{timestamp}.pkl")
    
    # 保存备份
    result = await graph_service.save_database(backup_path)
    print(f"备份完成: {result['file_path']}")

# 执行备份
asyncio.run(backup_database())
```

### 场景 2: 从备份恢复

```python
async def restore_from_backup():
    # 列出所有备份
    backups = await graph_service.list_database_files()
    
    # 选择最新的备份
    if backups:
        latest_backup = backups[0]
        result = await graph_service.load_database(
            Path(latest_backup['file_path'])
        )
        print(f"恢复完成: {result['message']}")

asyncio.run(restore_from_backup())
```

### 场景 3: 自动保存

自动保存功能默认启用，在以下情况会自动保存：
1. 任务完成时
2. 服务关闭前

可以通过 API 或代码控制：

```python
# 禁用自动保存
graph_service.set_auto_save(False)

# 处理大量任务...

# 手动保存
await graph_service.save_database()

# 重新启用自动保存
graph_service.set_auto_save(True)
```

## 事件通知

### 自动保存成功事件

当自动保存成功时，会通过 SSE 推送以下事件：

```json
{
  "event_type": "auto_save",
  "task_id": "task_xxx",
  "message": "数据库已自动保存",
  "file_path": "...",
  "file_size": 123456
}
```

### 自动保存失败事件

当自动保存失败时，会推送：

```json
{
  "event_type": "auto_save_error",
  "task_id": "task_xxx",
  "message": "数据库自动保存失败: ..."
}
```

## 数据格式

数据库文件使用 Python pickle 格式存储，包含以下内容：

```python
{
    "system": {
        "classes": {...},      # 类定义
        "base_entities": [...]  # 预定义实体
    },
    "entities": [...],         # 实体列表
    "class_nodes": [...],      # 类节点列表
    "class_master_nodes": [...],  # 类主节点列表
    "relationships": [...]     # 关系列表
}
```

## 注意事项

1. **文件大小**: 大型图谱可能产生较大的文件，建议定期清理旧备份
2. **版本兼容性**: pickle 文件可能不兼容不同版本的代码，升级前请备份
3. **并发访问**: 加载数据库会停止当前服务并重新初始化，谨慎在生产环境使用
4. **路径安全**: 自定义文件路径时注意路径合法性和权限问题
5. **自动保存频率**: 频繁的任务可能导致频繁保存，可考虑批量处理后手动保存

## 故障排查

### 问题 1: 保存失败

**症状**: 调用保存 API 返回错误

**可能原因**:
- 磁盘空间不足
- 目录权限不足
- SimpleGraph 未初始化

**解决方案**:
```python
# 检查服务状态
status = await graph_service.get_database_status()
print(f"服务已初始化: {status['initialized']}")

# 检查磁盘空间
import shutil
stat = shutil.disk_usage(graph_service.data_dir)
print(f"可用空间: {stat.free / (1024**3):.2f} GB")
```

### 问题 2: 加载失败

**症状**: 加载数据库时抛出异常

**可能原因**:
- 文件不存在或损坏
- 文件格式不兼容
- 文件被其他进程占用

**解决方案**:
```python
# 检查文件是否存在
from pathlib import Path
db_path = graph_service.get_default_database_path()
print(f"文件存在: {db_path.exists()}")
print(f"文件大小: {db_path.stat().st_size if db_path.exists() else 0}")

# 尝试加载并捕获详细错误
try:
    result = await graph_service.load_database()
except Exception as e:
    print(f"加载失败: {type(e).__name__}: {e}")
```

### 问题 3: 自动保存不工作

**症状**: 任务完成后没有自动保存

**可能原因**:
- 自动保存被禁用
- 任务未正常完成
- 保存过程中出现异常

**解决方案**:
```python
# 检查自动保存状态
status = await graph_service.get_database_status()
print(f"自动保存: {status['auto_save_enabled']}")

# 启用自动保存
graph_service.set_auto_save(True)

# 查看日志
# 检查日志中是否有 "自动保存成功" 或 "自动保存失败" 的消息
```

## 性能优化建议

1. **批量保存**: 处理大量任务时，考虑禁用自动保存，批量完成后手动保存
2. **异步操作**: 保存/加载操作是异步的，避免阻塞主线程
3. **文件压缩**: 对于大型图谱，可以考虑在保存后压缩文件
4. **增量保存**: 未来可以考虑实现增量保存机制，只保存变更部分

## 更新日志

### v1.0.0 (2024-01-09)
- 初始版本
- 添加基本的保存/加载功能
- 实现自动保存机制
- 提供完整的 REST API

## 相关文档

- [API 文档](./API_DOCUMENTATION.md)
- [快速开始](./QUICKSTART.md)
- [系统架构](../simple_graphrag/ARCHITECTURE_V2.md)
