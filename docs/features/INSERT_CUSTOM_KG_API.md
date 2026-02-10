# Feature: POST /insert_custom_kg API Endpoint

## 概述

为 LightRAG HTTP API 添加批量注入知识图谱的端点，支持一次性注入 chunks、entities 和 relationships。

## 背景

当前 LoomGraph 需要逐个调用：
- `POST /graph/entity/create` (每个实体)
- `POST /graph/relation/create` (每个关系)

对于大型代码库（10k+ 实体），这会产生大量 HTTP 请求，效率低下。

## API 规格

### 端点

```
POST /insert_custom_kg
```

### 请求格式

```json
{
  "custom_kg": {
    "chunks": [
      {
        "content": "def login(username, password): ...",
        "source_id": "auth.py:42",
        "file_path": "src/auth.py",
        "chunk_order_index": 0
      }
    ],
    "entities": [
      {
        "entity_name": "AuthService.login",
        "entity_type": "method",
        "description": "用户登录验证方法",
        "source_id": "auth.py:42",
        "file_path": "src/auth.py"
      }
    ],
    "relationships": [
      {
        "src_id": "AuthService.login",
        "tgt_id": "hashlib.sha256",
        "description": "调用 sha256 进行密码哈希",
        "keywords": "calls,dependency",
        "weight": 1.0,
        "source_id": "auth.py:42"
      }
    ]
  }
}
```

### 字段说明

#### chunks (可选)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content | string | ✅ | 代码/文本内容 |
| source_id | string | ✅ | 来源标识，用于关联 entities/relationships |
| file_path | string | ❌ | 文件路径，默认 "custom_kg" |
| chunk_order_index | int | ❌ | 顺序索引，默认 0 |

#### entities (可选)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| entity_name | string | ✅ | 实体名称 (唯一标识) |
| entity_type | string | ❌ | 类型，默认 "UNKNOWN" |
| description | string | ❌ | 描述，默认 "No description provided" |
| source_id | string | ❌ | 关联的 chunk source_id |
| file_path | string | ❌ | 文件路径 |

#### relationships (可选)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| src_id | string | ✅ | 源实体名称 |
| tgt_id | string | ✅ | 目标实体名称 |
| description | string | ✅ | 关系描述 |
| keywords | string | ✅ | 关键词，逗号分隔 |
| weight | float | ❌ | 权重，默认 1.0 |
| source_id | string | ❌ | 关联的 chunk source_id |
| file_path | string | ❌ | 文件路径 |

### 响应格式

#### 成功 (200)

```json
{
  "status": "success",
  "message": "Custom KG inserted successfully",
  "details": {
    "chunks_count": 10,
    "entities_count": 25,
    "relationships_count": 40
  }
}
```

#### 失败 (400/500)

```json
{
  "status": "error",
  "message": "Error description",
  "details": null
}
```

## 测试用例

### TC-01: 完整注入

**输入**: chunks + entities + relationships
**期望**: 200, 所有数据正确插入

### TC-02: 仅注入 entities

**输入**: 只有 entities，无 chunks/relationships
**期望**: 200, entities 正确插入

### TC-03: 仅注入 relationships

**输入**: 只有 relationships
**期望**: 200, 自动创建缺失的 src/tgt 节点

### TC-04: 空请求

**输入**: `{"custom_kg": {}}`
**期望**: 200, 无操作

### TC-05: 缺少必填字段

**输入**: entity 缺少 entity_name
**期望**: 400, 返回字段验证错误

### TC-06: 大批量注入

**输入**: 1000 entities + 2000 relationships
**期望**: 200, 性能 < 30s

### TC-07: 重复实体 (幂等性)

**输入**: 同一 entity_name 注入两次
**期望**: 200, 后者覆盖前者 (upsert)

## 验收标准

- [x] API 端点可访问
- [x] 请求/响应格式符合规格
- [x] 所有测试用例通过 (6/6 SDK 层)
- [x] 性能: 500 entities + 1000 relationships < 1s
- [x] 与现有 `ainsert_custom_kg` 方法逻辑一致
- [x] Swagger 文档自动生成

## 实现计划

1. ✅ 创建 Pydantic 请求/响应模型
2. ✅ 在 `document_routes.py` 添加路由
3. ✅ 调用 `rag.ainsert_custom_kg()`
4. ✅ 添加错误处理
5. ✅ 编写测试

## 相关代码

- `lightrag/lightrag.py:2255` - `ainsert_custom_kg()` 方法
- `lightrag/api/routers/document_routes.py:430-540` - Pydantic 模型
- `lightrag/api/routers/document_routes.py:2187-2250` - API 端点
- `tests/test_insert_custom_kg_api.py` - 测试用例
- `lightrag/api/routers/document_routes.py` - 路由定义
