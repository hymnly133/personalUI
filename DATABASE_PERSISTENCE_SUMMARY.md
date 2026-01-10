# 数据库持久化功能摘要

## 新增功能

为 GraphRAG 后端和核心逻辑添加了完整的数据库持久化功能。

## 文件更改

### 1. 新增目录
- `graphrag/backend/data/` - 数据存储目录

### 2. 核心逻辑更新
- `graphrag/simple_graphrag/simplegraph.py`
  - 添加 `load()` 类方法用于从文件加载图谱
  - 改进 `save()` 方法的日志输出

### 3. 后端服务更新
- `graphrag/backend/graph_service.py`
  - 添加 `data_dir` 属性指向数据目录
  - 添加 `auto_save_enabled` 属性控制自动保存
  - 添加 `save_database()` 方法保存数据库
  - 添加 `load_database()` 方法加载数据库
  - 添加 `list_database_files()` 方法列出数据库文件
  - 添加 `set_auto_save()` 方法配置自动保存
  - 添加 `get_default_database_path()` 方法获取默认路径
  - 更新 `_on_progress()` 方法实现任务完成后自动保存
  - 添加 `_auto_save_after_task()` 方法处理自动保存逻辑
  - 更新 `shutdown()` 方法在关闭前自动保存

### 4. API 端点新增
- `graphrag/backend/main.py`
  - `POST /api/database/save` - 保存数据库
  - `POST /api/database/load` - 加载数据库
  - `GET /api/database/list` - 列出数据库文件
  - `PUT /api/database/auto-save` - 配置自动保存
  - `GET /api/database/status` - 查询数据库状态

### 5. 文档
- `graphrag/backend/DATABASE_PERSISTENCE.md` - 完整的功能文档
- `graphrag/backend/test_database_persistence.py` - 测试脚本
- `graphrag/DATABASE_PERSISTENCE_SUMMARY.md` - 本摘要文档

## 主要特性

### 1. 手动保存/加载
```python
# 保存
result = await graph_service.save_database()

# 加载
result = await graph_service.load_database()
```

### 2. 自动保存
- 任务完成时自动保存（可配置）
- 服务关闭前自动保存
- 通过 SSE 推送保存事件

### 3. 文件管理
- 支持多个数据库文件
- 列出所有可用的数据库快照
- 支持自定义文件路径

### 4. API 支持
- RESTful API 完整支持
- 请求/响应模型完善
- 错误处理完整

## 使用示例

### 通过 API 保存数据库

```bash
# 保存到默认路径
curl -X POST http://localhost:8000/api/database/save \
  -H "Content-Type: application/json" \
  -d '{}'

# 保存到自定义文件
curl -X POST http://localhost:8000/api/database/save \
  -H "Content-Type: application/json" \
  -d '{"file_name": "backup_20240109.pkl"}'
```

### 通过 API 加载数据库

```bash
# 加载默认数据库
curl -X POST http://localhost:8000/api/database/load \
  -H "Content-Type: application/json" \
  -d '{}'

# 加载指定文件
curl -X POST http://localhost:8000/api/database/load \
  -H "Content-Type: application/json" \
  -d '{"file_name": "backup_20240109.pkl"}'
```

### 列出数据库文件

```bash
curl http://localhost:8000/api/database/list
```

### 配置自动保存

```bash
# 启用自动保存
curl -X PUT http://localhost:8000/api/database/auto-save \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# 禁用自动保存
curl -X PUT http://localhost:8000/api/database/auto-save \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### 查询数据库状态

```bash
curl http://localhost:8000/api/database/status
```

## 通过代码使用

### 保存和加载

```python
from pathlib import Path
from graph_service import graph_service

# 初始化服务
await graph_service.initialize()

# 保存数据库
result = await graph_service.save_database()
print(f"已保存: {result['file_path']}")

# 加载数据库
result = await graph_service.load_database()
print(f"已加载: {result['message']}")

# 列出所有数据库
databases = await graph_service.list_database_files()
for db in databases:
    print(f"{db['file_name']}: {db['file_size']} 字节")
```

### 使用 SimpleGraph 核心类

```python
from pathlib import Path
from simplegraph import SimpleGraph

# 创建并保存
sg = SimpleGraph(config_path=Path("config/config.yaml"))
await sg.start()
# ... 处理任务 ...
sg.save(Path("data/my_graph.pkl"))

# 从文件加载
sg = SimpleGraph.load(
    config_path=Path("config/config.yaml"),
    graph_path=Path("data/my_graph.pkl"),
    max_concurrent_tasks=3,
    enable_smart_merge=True
)
await sg.start()
```

## 数据格式

数据库文件使用 Python pickle 格式，包含：
- System 配置（类定义、预定义实体）
- Graph 数据（实体、关系、类节点）
- 所有元数据和时间戳

## 注意事项

1. **自动保存**: 默认启用，任务完成和服务关闭时触发
2. **文件大小**: 大型图谱可能产生较大文件
3. **版本兼容**: pickle 格式可能不兼容不同版本
4. **并发安全**: 加载操作会重启服务，注意使用时机
5. **路径权限**: 确保数据目录有读写权限

## 测试

运行测试脚本验证功能：

```bash
cd graphrag/backend
python test_database_persistence.py
```

测试包括：
- 服务初始化
- 任务提交和完成
- 数据库保存
- 文件列表
- 数据库加载
- 数据验证
- 自动保存配置

## 未来改进

可能的增强方向：
1. 增量保存（只保存变更）
2. 压缩支持（减小文件大小）
3. 版本管理（支持回滚）
4. 远程存储（S3、云存储）
5. 加密支持（敏感数据保护）

## 相关文档

- [完整文档](./backend/DATABASE_PERSISTENCE.md)
- [API 文档](./backend/API_DOCUMENTATION.md)
- [快速开始](./backend/QUICKSTART.md)
