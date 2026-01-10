# SmartMerger 增强优化报告

## 优化日期
2026-01-10

## 问题分析

### 原有问题
1. **数据不完整**: SmartMerger在调用LLM进行智能合并时，只提供了前20个实体的简单信息，没有提供完整的现有图谱数据
2. **缺少搜索机制**: 没有为delta中的实体进行搜索，导致LLM无法准确判断实体是否已存在
3. **上下文不足**: LLM难以做出准确的合并决策，容易将已存在的实体标记为新实体（operation="add"）

## 优化方案

### 1. 增强数据准备 (`smart_merger.py`)

#### 1.1 新增方法：`_get_all_entities_detail()`

**功能**: 获取所有现有实体的完整详情（不包含关系）

**返回数据结构**:
```json
[
  {
    "name": "微信",
    "description": "即时通讯应用",
    "classes": ["可启动应用", "交流平台"],
    "properties": {
      "可启动应用": {
        "启动方式": "点击图标"
      }
    }
  }
]
```

**特点**:
- 返回**所有**实体（不再限制数量）
- 包含完整的类信息
- 包含所有属性值
- 不包含关系（关系数据量大，且LLM主要需要实体信息来判断重复）

#### 1.2 新增方法：`_search_related_entities_for_delta()`

**功能**: 为delta中的每个实体进行模糊搜索，找到可能相关的现有实体

**工作流程**:
1. 遍历delta中的每个实体
2. 使用实体名称进行模糊搜索（fuzzy=True）
3. 收集搜索结果中的所有相关实体
4. 去重合并（同一个现有实体可能被多个delta实体搜索到）
5. 按相关度（search_score）排序

**返回数据结构**:
```json
[
  {
    "name": "微信",
    "description": "即时通讯应用",
    "classes": ["可启动应用", "交流平台"],
    "properties": {},
    "search_score": 1.0,
    "matched_by": "微信"
  },
  {
    "name": "美团外卖",
    "description": "外卖订餐平台",
    "classes": ["可启动应用"],
    "properties": {},
    "search_score": 0.9,
    "matched_by": "美团"
  }
]
```

**关键字段**:
- `search_score`: 相关度得分（0-1），越高越相关
- `matched_by`: 该现有实体是通过搜索delta中的哪个实体找到的

**优势**:
- 精准定位相关实体
- 支持模糊匹配（例如："美团"可以匹配到"美团外卖"）
- 提供相关度评分，帮助LLM判断
- 记录匹配来源，便于LLM理解关联关系

### 2. 优化LLM输入

#### 2.1 修改`_llm_merge()`方法

**原有参数**:
```python
existing_entities=", ".join(existing_entities),  # 只有实体名称列表
existing_entities_detail=existing_entities_detail,  # 前20个实体
```

**新增参数**:
```python
existing_entities_full=existing_entities_full,  # 所有实体的完整信息
delta_related_data=delta_related_data,  # delta相关的搜索结果
```

#### 2.2 LLM输入数据对比

| 数据项 | 原有 | 优化后 |
|--------|------|--------|
| 实体列表 | 前50个名称 | ❌ 已移除 |
| 实体详情 | 前20个 | **所有**实体完整信息 |
| 搜索结果 | ❌ 无 | ✅ 针对delta的搜索结果 |
| 属性值 | ❌ 无 | ✅ 包含所有属性 |

### 3. 优化提示词 (`smart_merge.txt`)

#### 3.1 新增数据说明部分

```markdown
### 所有现有实体详情（完整列表，不包含关系）
以下是当前图谱中的所有实体信息...

### Delta相关的现有数据（模糊搜索结果）
以下是通过对待合并delta中每个实体进行模糊搜索后，
找到的可能相关的现有实体...
```

#### 3.2 增强合并任务说明

新增**数据理解与对照**部分，明确指导LLM如何使用提供的数据：

1. 先查看"Delta相关的现有数据"中是否有相关实体
2. 利用`search_score`和`matched_by`字段判断相关性
3. 到"所有现有实体详情"中查看完整信息
4. 基于完整信息做出合并决策

#### 3.3 添加完整示例

提供了详细的示例，展示：
- 如何利用搜索结果判断实体是否存在
- 正确的决策流程
- 常见错误和正确做法对比

## 测试验证

### 测试脚本
`test_smart_merger_enhanced.py`

### 测试结果

✅ **所有测试通过**

测试输出：
```
[3.2] 测试_search_related_entities_for_delta...
   搜索到相关实体数量: 2
   相关实体:
      - 微信 (score=1.00, matched_by=微信)
      - 美团外卖 (score=0.90, matched_by=美团)
   是否找到'微信': True
   是否找到包含'美团'的实体: True
```

**关键验证点**:
1. ✅ 精确匹配：delta中的"微信"正确搜索到现有的"微信"（score=1.0）
2. ✅ 模糊匹配：delta中的"美团"正确搜索到现有的"美团外卖"（score=0.9）
3. ✅ matched_by字段正确记录匹配来源
4. ✅ 去重功能正常工作

## 优化效果

### 1. 数据完整性
- **优化前**: 只有前20个实体的基本信息
- **优化后**: 所有实体的完整信息（包含属性）

### 2. 搜索能力
- **优化前**: 无搜索功能
- **优化后**: 自动为每个delta实体搜索相关数据，支持模糊匹配

### 3. LLM判断准确性
- **优化前**: LLM缺少足够信息，容易将已存在实体误判为新实体
- **优化后**: 
  - 提供完整的现有实体列表
  - 提供针对性的搜索结果
  - 提供相关度评分
  - LLM可以做出更准确的判断

### 4. 性能考虑

**搜索性能**:
- 每个delta实体最多搜索10个结果（可配置）
- 使用SearchEngine的智能去重和排序
- 搜索结果按相关度排序，高相关实体优先

**数据量控制**:
- 虽然返回所有实体，但不包含关系数据
- 只包含必要的属性信息
- JSON格式紧凑

## 向后兼容性

✅ **完全向后兼容**

- 保留了原有的`_get_entities_detail()`方法
- 新增方法不影响现有功能
- 提示词增强但保持格式兼容

## 使用示例

### LLM收到的数据示例

```json
{
  "existing_entities_full": [
    {
      "name": "微信",
      "description": "即时通讯应用",
      "classes": ["可启动应用", "交流平台"],
      "properties": {}
    },
    {
      "name": "美团外卖",
      "description": "外卖订餐平台",
      "classes": ["可启动应用"],
      "properties": {}
    }
  ],
  "delta_related_data": [
    {
      "name": "微信",
      "description": "即时通讯应用",
      "classes": ["可启动应用", "交流平台"],
      "properties": {},
      "search_score": 1.0,
      "matched_by": "微信"
    },
    {
      "name": "美团外卖",
      "description": "外卖订餐平台",
      "classes": ["可启动应用"],
      "properties": {},
      "search_score": 0.9,
      "matched_by": "美团"
    }
  ]
}
```

### LLM的正确判断

对于delta实体"微信"：
1. 在`delta_related_data`中发现"微信"（score=1.0）
2. 名称完全匹配，说明实体已存在
3. 在`existing_entities_full`中查看完整信息
4. **决策**: operation="update"（而非"add"）

对于delta实体"美团"：
1. 在`delta_related_data`中发现"美团外卖"（score=0.9）
2. 名称相似，很可能是同一实体
3. 在`existing_entities_full`中确认"美团外卖"的完整信息
4. **决策**: operation="update", name="美团外卖"（使用现有名称）

## 相关文件

### 修改的文件
1. `src/combiners/smart_merger.py` - 核心逻辑增强
2. `config/prompts/smart_merge.txt` - 提示词优化

### 新增的文件
3. `test_smart_merger_enhanced.py` - 功能测试

### 文档
4. `SMART_MERGER_ENHANCEMENT.md` - 本文档

## 后续建议

1. **性能监控**: 在实际使用中监控搜索性能，必要时优化搜索限制
2. **提示词调优**: 根据LLM的实际输出效果，继续调优提示词
3. **搜索算法**: 考虑使用更高级的相似度算法（如编辑距离、语义相似度）
4. **缓存机制**: 对于频繁搜索的实体，可以考虑添加缓存

## 总结

本次优化通过以下三个方面大幅提升了SmartMerger的合并准确性：

1. **完整性**: 提供所有现有实体的完整信息
2. **智能性**: 自动搜索相关实体，支持模糊匹配
3. **可理解性**: 增强提示词，明确指导LLM如何使用数据

优化后，LLM能够：
- 准确识别已存在的实体
- 正确判断实体间的相似关系
- 做出更合理的合并决策
- 减少重复实体的创建

这将显著提高知识图谱的数据质量和一致性。
