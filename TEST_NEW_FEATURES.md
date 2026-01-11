# 测试新功能清单

## 快速测试指南

### 测试前准备

```bash
# 1. 确保环境变量已配置
cd graphrag/backend

# 2. 检查 .env 文件
cat .env  # 确保有 MIMO_API_KEY 等配置

# 3. 启动后端服务
python main.py
```

---

## 测试 1: 自动加载功能

### 步骤

1. **停止服务**（如果正在运行）
2. **确保默认数据库存在**：
   ```bash
   ls data/graph_database.pkl
   ```
3. **启动服务**：
   ```bash
   python main.py
   ```

### 预期结果

日志应显示：
```
[INFO] 检测到默认数据库文件，正在加载: .../data/graph_database.pkl
[INFO] 已从默认数据库加载: X 个实体
[INFO] SimpleGraph service initialized and started.
```

### 验证

```bash
# 查询数据库状态
curl http://localhost:8000/api/database/status

# 查询统计信息
curl http://localhost:8000/api/stats
```

---

## 测试 2: 自动保存功能

### 步骤

1. **提交一个测试任务**：
   ```bash
   curl -X POST http://localhost:8000/api/tasks \
     -H "Content-Type: application/json" \
     -d '{
       "input_text": "小红书是一个生活方式平台，成立于2013年。"
     }'
   ```

2. **等待任务完成**（通过日志或SSE事件监控）

### 预期结果

任务完成后，日志应显示：
```
[INFO] 任务 xxxx 完成，开始自动保存数据库...
[INFO] 数据库保存成功: .../data/graph_database.pkl
[INFO] 自动保存成功: ...
```

### 验证

```bash
# 检查文件修改时间
ls -la data/graph_database.pkl

# 查看文件大小是否变化
```

---

## 测试 3: 新建数据库

### 通过 API

```bash
# 新建数据库
curl -X POST http://localhost:8000/api/database/create \
  -H "Content-Type: application/json" \
  -d '{"file_name": "test_new.pkl"}'
```

### 预期结果

```json
{
  "success": true,
  "file_path": ".../data/test_new.pkl",
  "file_name": "test_new.pkl",
  "statistics": {
    "system": {"classes": X, ...},
    "graph": {"entities": 0, "relationships": 0}
  },
  "message": "新数据库已创建并保存到 ..."
}
```

### 验证

```bash
# 检查文件是否创建
ls data/test_new.pkl

# 列出所有数据库
curl http://localhost:8000/api/database/list
```

---

## 测试 4: 数据库管理操作

### 4.1 保存数据库

```bash
curl -X POST http://localhost:8000/api/database/save \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 4.2 加载数据库

```bash
curl -X POST http://localhost:8000/api/database/load \
  -H "Content-Type: application/json" \
  -d '{"file_name": "test_new.pkl"}'
```

### 4.3 重命名数据库

```bash
curl -X PUT http://localhost:8000/api/database/rename \
  -H "Content-Type: application/json" \
  -d '{
    "old_name": "test_new.pkl",
    "new_name": "test_renamed.pkl"
  }'
```

### 4.4 删除数据库

```bash
# 注意：不能删除当前使用的数据库
curl -X DELETE http://localhost:8000/api/database/test_renamed.pkl
```

---

## 测试 5: 前端界面

### 步骤

1. **启动前端**：
   ```bash
   cd graphrag/frontend
   npm run dev
   ```

2. **打开浏览器**：
   ```
   http://localhost:5173
   ```

3. **点击 "Database" 标签页**

### 验证项

- [ ] 显示数据库状态（已初始化）
- [ ] 显示自动保存开关（可切换）
- [ ] 显示统计信息（类、实体、关系数量）
- [ ] 显示数据库列表
- [ ] 当前数据库有 "当前" 标签
- [ ] 可以新建数据库
- [ ] 可以保存当前数据库
- [ ] 可以加载其他数据库
- [ ] 可以重命名数据库
- [ ] 可以删除数据库（除了当前）
- [ ] 加载数据库后图谱自动刷新

---

## 测试 6: 服务关闭自动保存

### 步骤

1. **提交任务并等待完成**
2. **按 Ctrl+C 关闭服务**

### 预期结果

关闭前日志应显示：
```
[INFO] 停止任务处理器...
[INFO] 服务关闭前已自动保存数据库
[INFO] 任务处理器已停止
```

---

## 测试 7: 自动保存开关

### 步骤

1. **禁用自动保存**：
   ```bash
   curl -X PUT http://localhost:8000/api/database/auto-save \
     -H "Content-Type: application/json" \
     -d '{"enabled": false}'
   ```

2. **提交任务并等待完成**

3. **检查日志** - 不应该有自动保存消息

4. **启用自动保存**：
   ```bash
   curl -X PUT http://localhost:8000/api/database/auto-save \
     -H "Content-Type: application/json" \
     -d '{"enabled": true}'
   ```

---

## 测试 8: 错误处理

### 8.1 加载不存在的数据库

```bash
curl -X POST http://localhost:8000/api/database/load \
  -H "Content-Type: application/json" \
  -d '{"file_name": "nonexistent.pkl"}'
```

**预期**: 404 错误，提示文件不存在

### 8.2 删除当前数据库

```bash
curl -X DELETE http://localhost:8000/api/database/graph_database.pkl
```

**预期**: 400 错误，提示不能删除当前数据库

### 8.3 重命名到已存在的文件

```bash
curl -X PUT http://localhost:8000/api/database/rename \
  -H "Content-Type: application/json" \
  -d '{
    "old_name": "test1.pkl",
    "new_name": "graph_database.pkl"
  }'
```

**预期**: 400 错误，提示目标文件已存在

---

## 测试 9: 完整工作流

### 场景：从头开始创建项目

1. **创建新数据库**
   ```bash
   curl -X POST http://localhost:8000/api/database/create \
     -H "Content-Type: application/json" \
     -d '{"file_name": "my_project.pkl"}'
   ```

2. **提交第一个任务**
   ```bash
   curl -X POST http://localhost:8000/api/tasks \
     -H "Content-Type: application/json" \
     -d '{"input_text": "这是我的第一个任务..."}'
   ```

3. **等待任务完成** → 自动保存

4. **提交更多任务** → 每次自动保存

5. **查看数据库列表**
   ```bash
   curl http://localhost:8000/api/database/list
   ```

6. **备份当前数据库**
   ```bash
   curl -X POST http://localhost:8000/api/database/save \
     -H "Content-Type: application/json" \
     -d '{"file_name": "backup_20240109.pkl"}'
   ```

7. **关闭服务** → 自动保存

---

## 快速验证脚本

将以下脚本保存为 `test_all.sh`：

```bash
#!/bin/bash

API_BASE="http://localhost:8000"

echo "=== 测试 1: 查询数据库状态 ==="
curl -s $API_BASE/api/database/status | jq

echo -e "\n=== 测试 2: 列出数据库文件 ==="
curl -s $API_BASE/api/database/list | jq

echo -e "\n=== 测试 3: 创建新数据库 ==="
curl -s -X POST $API_BASE/api/database/create \
  -H "Content-Type: application/json" \
  -d '{"file_name": "test_'$(date +%s)'.pkl"}' | jq

echo -e "\n=== 测试 4: 再次列出数据库 ==="
curl -s $API_BASE/api/database/list | jq

echo -e "\n=== 测试 5: 保存当前数据库 ==="
curl -s -X POST $API_BASE/api/database/save \
  -H "Content-Type: application/json" \
  -d '{}' | jq

echo -e "\n=== 所有测试完成 ==="
```

运行：
```bash
chmod +x test_all.sh
./test_all.sh
```

---

## 测试检查清单

### 后端功能
- [ ] 服务启动自动加载默认数据库
- [ ] 任务完成后自动保存
- [ ] 服务关闭前自动保存
- [ ] 新建数据库 API
- [ ] 保存数据库 API
- [ ] 加载数据库 API
- [ ] 重命名数据库 API
- [ ] 删除数据库 API
- [ ] 列出数据库 API
- [ ] 查询状态 API
- [ ] 自动保存开关 API

### 前端功能
- [ ] 数据库管理标签页
- [ ] 状态显示
- [ ] 统计信息显示
- [ ] 数据库列表显示
- [ ] 新建数据库对话框
- [ ] 保存按钮
- [ ] 加载按钮
- [ ] 重命名对话框
- [ ] 删除确认对话框
- [ ] 自动保存开关
- [ ] 刷新按钮
- [ ] 加载后自动刷新图谱

### 错误处理
- [ ] 文件不存在错误
- [ ] 删除当前数据库错误
- [ ] 重命名冲突错误
- [ ] 权限错误
- [ ] 网络错误

### 用户体验
- [ ] 操作反馈消息
- [ ] 加载状态指示
- [ ] 确认对话框
- [ ] 错误提示友好
- [ ] 界面响应迅速

---

## 报告问题

如果发现任何问题，请记录：

1. **问题描述**
2. **重现步骤**
3. **预期结果**
4. **实际结果**
5. **日志输出**
6. **环境信息**（操作系统、浏览器等）

---

## 成功标准

所有测试项都通过 ✅ 即表示功能正常！

祝测试顺利！🎉
