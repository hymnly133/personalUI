# 数据库管理功能更新说明

## 更新概述

本次更新为 GraphRAG 系统添加了完整的数据库管理功能，包括：
1. ✅ **自动加载** - 服务启动时自动加载默认数据库
2. ✅ **自动保存** - 任务完成和服务关闭时自动保存
3. ✅ **手动管理** - 新建、保存、加载、重命名、删除数据库
4. ✅ **前端界面** - 完整的可视化数据库管理界面

---

## 问题解答

### Q1: 现在可以自动加载和保存在默认路径吗？

**是的！** ✅

#### 自动加载
- **启动加载**: 服务启动时会自动检测默认路径 `graphrag/backend/data/graph_database.pkl`
- **智能处理**: 
  - 如果文件存在，自动加载
  - 如果不存在或加载失败，创建新的空数据库
  - 加载失败时会记录日志并回退到新数据库

#### 自动保存
- **任务完成**: 每个任务完成后自动保存（可配置）
- **服务关闭**: 服务关闭前自动保存
- **实时通知**: 通过 SSE 推送保存成功/失败事件
- **开关控制**: 可以通过 API 或前端界面开启/关闭

---

## 新增功能详细说明

### 1. 后端新增功能

#### 1.1 自动加载机制

```python
# graph_service.py
async def initialize(self, auto_load: bool = True):
    """
    初始化时自动加载默认数据库
    
    - 检测默认路径的数据库文件
    - 如果存在则加载
    - 如果不存在或失败则创建新数据库
    """
```

**特点**：
- 默认开启自动加载
- 失败自动降级（fallback）
- 详细的日志记录

#### 1.2 新建数据库方法

```python
async def create_new_database(self, file_name: Optional[str] = None):
    """
    创建新的空数据库
    
    - 停止当前服务
    - 创建新的 SimpleGraph 实例
    - 保存到指定路径
    """
```

**API 端点**: `POST /api/database/create`

#### 1.3 数据库管理方法

| 方法 | 功能 | API端点 |
|------|------|---------|
| `delete_database()` | 删除数据库文件 | `DELETE /api/database/{file_name}` |
| `rename_database()` | 重命名数据库文件 | `PUT /api/database/rename` |
| `save_database()` | 保存当前数据库 | `POST /api/database/save` |
| `load_database()` | 加载指定数据库 | `POST /api/database/load` |
| `list_database_files()` | 列出所有数据库 | `GET /api/database/list` |

### 2. 前端新增功能

#### 2.1 数据库管理界面

新增 `DatabaseManager.vue` 组件，提供完整的可视化管理界面。

**功能包括**：

1. **状态监控**
   - 显示初始化状态
   - 显示自动保存开关
   - 显示当前统计信息（类、实体、关系数量）

2. **数据库列表**
   - 显示所有可用数据库
   - 标记当前使用的数据库
   - 显示文件大小和修改时间
   - 支持排序和搜索

3. **操作功能**
   - 🆕 新建数据库
   - 💾 保存当前数据库
   - 📂 加载数据库
   - ✏️ 重命名数据库
   - 🗑️ 删除数据库
   - 🔄 刷新列表

#### 2.2 界面截图说明

```
┌─────────────────────────────────────────┐
│  数据库管理                        🔄 刷新 │
├─────────────────────────────────────────┤
│  当前状态: ✅ 已初始化                   │
│  自动保存: 🟢 开启                       │
│  默认路径: .../data/graph_database.pkl  │
├─────────────────────────────────────────┤
│  统计信息                                │
│  类定义: 5  |  实体: 10  |  关系: 15    │
├─────────────────────────────────────────┤
│  🆕 新建数据库   💾 保存当前数据库      │
├─────────────────────────────────────────┤
│  可用数据库 (3)                          │
│  ┌─────────────────────────────────┐   │
│  │ graph_database.pkl  [当前] 📂✏️🗑️│   │
│  │ backup_20240109.pkl        📂✏️🗑️│   │
│  │ test.pkl                  📂✏️🗑️│   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

## 使用指南

### 1. 启动服务（自动加载）

```bash
# 进入后端目录
cd graphrag/backend

# 启动服务（会自动加载默认数据库）
python main.py
```

**日志输出示例**：
```
[INFO] 检测到默认数据库文件，正在加载: .../data/graph_database.pkl
[INFO] 已从默认数据库加载: 10 个实体
[INFO] SimpleGraph service initialized and started.
```

### 2. 前端使用

1. 打开浏览器访问前端
2. 点击 **"Database"** 标签页
3. 查看当前数据库状态
4. 进行数据库管理操作

### 3. API 使用示例

#### 创建新数据库

```bash
# 使用默认名称
curl -X POST http://localhost:8000/api/database/create \
  -H "Content-Type: application/json" \
  -d '{}'

# 指定名称
curl -X POST http://localhost:8000/api/database/create \
  -H "Content-Type: application/json" \
  -d '{"file_name": "my_new_database.pkl"}'
```

#### 加载数据库

```bash
curl -X POST http://localhost:8000/api/database/load \
  -H "Content-Type: application/json" \
  -d '{"file_name": "backup_20240109.pkl"}'
```

#### 重命名数据库

```bash
curl -X PUT http://localhost:8000/api/database/rename \
  -H "Content-Type: application/json" \
  -d '{
    "old_name": "test.pkl",
    "new_name": "production.pkl"
  }'
```

#### 删除数据库

```bash
curl -X DELETE http://localhost:8000/api/database/test.pkl
```

---

## 配置说明

### 默认路径配置

默认数据库路径: `graphrag/backend/data/graph_database.pkl`

可以通过以下方式修改：
```python
# 在 graph_service.py 中
self.data_dir = Path(__file__).parent / "data"  # 修改这里
```

### 自动保存配置

#### 通过 API 配置

```bash
# 启用
curl -X PUT http://localhost:8000/api/database/auto-save \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# 禁用
curl -X PUT http://localhost:8000/api/database/auto-save \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

#### 通过前端配置

在数据库管理界面中，直接切换"自动保存"开关。

---

## 工作流示例

### 场景 1: 日常使用（自动管理）

1. **启动服务** → 自动加载最新数据库
2. **提交任务** → 处理数据
3. **任务完成** → 自动保存
4. **关闭服务** → 自动保存

**完全自动化，无需手动干预！** 🎉

### 场景 2: 创建新项目

1. 点击 **"新建数据库"**
2. 输入项目名称（如 `project_alpha.pkl`）
3. 确认创建
4. 开始处理新数据

### 场景 3: 备份和恢复

#### 备份

```bash
# 方法1: 通过API保存到新文件
curl -X POST http://localhost:8000/api/database/save \
  -H "Content-Type: application/json" \
  -d '{"file_name": "backup_20240109.pkl"}'

# 方法2: 直接复制文件
cp graphrag/backend/data/graph_database.pkl \
   graphrag/backend/data/backup_20240109.pkl
```

#### 恢复

1. 在前端数据库列表中找到备份文件
2. 点击 **"加载"** 按钮
3. 确认加载
4. 图谱自动刷新

### 场景 4: 多环境管理

```bash
# 开发环境
dev_database.pkl

# 测试环境
test_database.pkl

# 生产环境
production_database.pkl
```

在前端界面中快速切换不同环境的数据库。

---

## 安全注意事项

1. **删除保护**: 不能删除当前正在使用的数据库
2. **加载确认**: 加载数据库前需要确认，防止误操作
3. **自动备份**: 建议定期创建备份文件
4. **权限管理**: 确保数据目录有适当的读写权限

---

## 故障排查

### 问题 1: 服务启动时没有加载数据库

**可能原因**：
- 数据库文件不存在
- 文件损坏
- 权限问题

**解决方案**：
```bash
# 检查文件是否存在
ls graphrag/backend/data/graph_database.pkl

# 查看日志
# 日志会显示是否尝试加载以及失败原因
```

### 问题 2: 自动保存不工作

**检查步骤**：
1. 查看数据库状态：`GET /api/database/status`
2. 确认 `auto_save_enabled` 为 `true`
3. 查看日志中是否有保存成功消息

**解决方案**：
```bash
# 通过API启用自动保存
curl -X PUT http://localhost:8000/api/database/auto-save \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### 问题 3: 加载数据库后图谱不更新

**原因**: 前端需要手动刷新

**解决方案**: 
- 前端已集成自动刷新功能
- 加载成功后会自动刷新图谱
- 如果没有自动刷新，手动点击刷新按钮

---

## 性能优化建议

1. **定期清理**: 删除不再需要的旧数据库文件
2. **文件命名**: 使用有意义的命名方式（如带时间戳）
3. **备份策略**: 
   - 每日备份: `daily_20240109.pkl`
   - 里程碑备份: `milestone_v1.0.pkl`
4. **监控大小**: 定期检查数据库文件大小，及时优化

---

## 技术细节

### 数据持久化格式

使用 Python pickle 序列化：

```python
{
    "system": {
        "classes": {...},
        "base_entities": [...]
    },
    "entities": [...],
    "class_nodes": [...],
    "relationships": [...]
}
```

### 自动加载流程

```
启动服务
    ↓
检查默认路径是否存在数据库文件
    ↓
    ├─ 存在 → 尝试加载
    │     ↓
    │  加载成功 → 使用加载的数据库
    │     ↓
    │  加载失败 → 记录日志 → 创建新数据库
    │
    └─ 不存在 → 创建新数据库
```

### 自动保存触发点

1. **任务完成时**
   ```python
   # 在 _on_progress() 中
   if step == "completed" and self.auto_save_enabled:
       asyncio.create_task(self._auto_save_after_task(task_id))
   ```

2. **服务关闭时**
   ```python
   # 在 shutdown() 中
   if self.auto_save_enabled:
       await self.save_database()
   ```

---

## 更新日志

### v1.1.0 (2024-01-09)

**新增功能**：
- ✅ 服务启动时自动加载默认数据库
- ✅ 任务完成后自动保存
- ✅ 服务关闭前自动保存
- ✅ 新建数据库方法
- ✅ 重命名数据库方法
- ✅ 删除数据库方法
- ✅ 完整的前端管理界面

**改进**：
- 🔧 优化错误处理和日志记录
- 🔧 增强安全性（删除保护、确认对话框）
- 🔧 改进用户体验（实时通知、自动刷新）

---

## 相关文档

- [数据库持久化完整文档](./backend/DATABASE_PERSISTENCE.md)
- [数据库持久化功能摘要](./DATABASE_PERSISTENCE_SUMMARY.md)
- [API 文档](./backend/API_DOCUMENTATION.md)
- [快速开始](./backend/QUICKSTART.md)

---

## 总结

本次更新实现了完整的数据库自动管理功能：

✅ **启动时自动加载** - 无需手动加载  
✅ **任务后自动保存** - 无需担心数据丢失  
✅ **关闭前自动保存** - 安全退出  
✅ **前端可视化管理** - 操作简单直观  
✅ **完整的API支持** - 灵活集成  

现在你可以专注于处理数据，系统会自动管理数据库的保存和加载！🎉
