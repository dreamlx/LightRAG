# LoomGraph Integration API Reference

LightRAG fork endpoints used by LoomGraph for code knowledge graph workflows.

All endpoints support workspace routing via `LIGHTRAG-WORKSPACE` header.

## Storage Architecture

`insert_custom_kg` writes to **all three storage layers** in a single API call:

| Storage Layer | 写入内容 | 查询端点 |
|---|---|---|
| **Graph** (AGE/NetworkX) | entities (upsert_node) + relations (upsert_edge) | `/graph/entities/all`, `/graph/relations/all` |
| **Vector** (pgvector) | entities_vdb + relationships_vdb + chunks_vdb | `/query` (RAG) |
| **KV** (chunks) | text_chunks (代码文本) | `/query` (RAG context) |

对比各端点的写入范围：

| 操作 | Graph | Vector (entity/relation) | Vector (chunks) | KV (chunks) |
|---|:-:|:-:|:-:|:-:|
| `POST /graph/entity/create` | upsert_node | entities_vdb | - | - |
| `POST /graph/relation/create` | upsert_edge | relationships_vdb | - | - |
| `POST /documents/insert_custom_kg` | upsert_node + upsert_edge | entities_vdb + relationships_vdb + chunks_vdb | chunks_vdb | text_chunks |

**结论**: `insert_custom_kg` 是 `entity/create` + `relation/create` 的**超集**，一次调用写入全部层。

> 验证记录 (2026-02-21): 通过 `insert_custom_kg` 注入 3 entities + 2 relations，在 `/graph/entities/all` 和 `/graph/relations/all` 中全部查到。注入耗时 0.55s。

## Cold Rebuild Flow

```bash
# 1. Clear all data for workspace
curl -X DELETE http://host:port/graph/clear \
  -H "LIGHTRAG-WORKSPACE: loomgraph_demo"

# 2. Wait for async storage cleanup (3s recommended)
sleep 3

# 3. Inject knowledge graph (all layers in one call)
curl -X POST http://host:port/documents/insert_custom_kg \
  -H "LIGHTRAG-WORKSPACE: loomgraph_demo" \
  -H "Content-Type: application/json" \
  -d '{"custom_kg": {"chunks": [...], "entities": [...], "relationships": [...]}}'

# 4. Verify graph layer
curl http://host:port/graph/entities/all \
  -H "LIGHTRAG-WORKSPACE: loomgraph_demo"

# 5. Verify RAG layer (optional)
curl -X POST http://host:port/query \
  -H "LIGHTRAG-WORKSPACE: loomgraph_demo" \
  -H "Content-Type: application/json" \
  -d '{"query": "What does AuthService do?", "mode": "local"}'
```

**注意事项**:
- `/graph/clear` 是异步清理，返回成功后存储可能仍在清理中，建议等待 3 秒
- Workspace 名称必须全小写（大写名称会导致 entity 只进入 vector storage，不进 graph storage）

## Incremental Update Flow

```bash
# 1. Delete old data for changed files
curl -X DELETE http://host:port/graph/by_source \
  -H "LIGHTRAG-WORKSPACE: loomgraph_demo" \
  -H "Content-Type: application/json" \
  -d '{"source_ids": ["src/auth/service.py", "src/auth/utils.py"]}'

# 2. Re-inject only changed files
curl -X POST http://host:port/documents/insert_custom_kg \
  -H "LIGHTRAG-WORKSPACE: loomgraph_demo" \
  -H "Content-Type: application/json" \
  -d '{"custom_kg": {"chunks": [...], "entities": [...], "relationships": [...]}}'
```

按 `source_id` 精确删除 + 重新注入变动文件，无需全量重建。

## Core Endpoints

### DELETE /graph/clear

Clear all storage data for a workspace. Drops all 11 storage backends in parallel. Does NOT delete `llm_response_cache` (reusable across rebuilds). Does NOT delete input directory files.

**Response:**
```json
{
  "status": "success",
  "workspace": "loomgraph_demo",
  "storages_cleared": 11,
  "errors": null
}
```

**Error codes:**
- `409` — Pipeline is busy (indexing in progress)
- `500` — All storage drops failed

### DELETE /graph/by_source

Delete all entities, relations, and chunks associated with given source_ids. Enables incremental updates without full rebuild. Cleans all storage layers (graph + vector + KV).

**Request:**
```json
{
  "source_ids": ["src/auth/service.py", "src/auth/utils.py"]
}
```

**Response:**
```json
{
  "status": "success",
  "workspace": "loomgraph_demo",
  "deleted": {
    "entities": 15,
    "relations": 23,
    "chunks": 8
  }
}
```

**Error codes:**
- `400` — Missing or invalid `source_ids`
- `500` — Internal error during deletion

### POST /documents/insert_custom_kg

Inject pre-built knowledge graph into **all storage layers** (graph + vector + KV), bypassing LLM extraction. This is the **primary data ingestion path** for LoomGraph.

**Request:**
```json
{
  "custom_kg": {
    "chunks": [
      {
        "content": "def hello(): ...",
        "source_id": "src/main.py",
        "tokens": 50,
        "chunk_order_index": 0,
        "full_doc_id": "src/main.py"
      }
    ],
    "entities": [
      {
        "entity_name": "hello",
        "entity_type": "function",
        "description": "A greeting function",
        "source_id": "src/main.py"
      }
    ],
    "relationships": [
      {
        "src_id": "main",
        "tgt_id": "hello",
        "description": "module main defines function hello",
        "keywords": "CALLS",
        "weight": 1.0,
        "source_id": "src/main.py"
      }
    ]
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Custom KG inserted successfully",
  "details": {
    "chunks_count": 1,
    "entities_count": 1,
    "relationships_count": 1,
    "workspace": "loomgraph_demo"
  }
}
```

### POST /graph/entity/create

Create a single entity (graph + entity vector). Use `insert_custom_kg` instead for batch operations.

**Request:**
```json
{
  "entity_name": "hello",
  "entity_type": "function",
  "description": "A greeting function",
  "source_id": "src/main.py"
}
```

**Response:**
```json
{
  "status": "success",
  "entity_name": "hello",
  "graph_data": {"entity_id": "..."}
}
```

**已知问题**: 如果 workspace 名称包含大写字母，`graph_data` 可能返回 `null`。务必使用全小写 workspace 名称。

### POST /graph/relation/create

Create a single relation (graph + relation vector). Use `insert_custom_kg` instead for batch operations.

**Request:**
```json
{
  "src_id": "main",
  "tgt_id": "hello",
  "description": "module main defines function hello",
  "keywords": "CALLS",
  "weight": 1.0,
  "source_id": "src/main.py"
}
```

**Response:**
```json
{
  "status": "success",
  "source": "main",
  "target": "hello"
}
```

**约束**: 同一 `(src_id, tgt_id, keywords)` 组合不允许重复，重复创建返回 "already exists" 错误。

## Export Endpoints

### GET /graph/entities/all

Returns all entity nodes from the graph storage.

**Response:** `List[dict]` — each dict contains entity properties (`entity_name`, `entity_type`, `description`, `source_id`, etc.). The `content_vector` field is stripped from responses.

### GET /graph/relations/all

Returns all relation edges from the graph storage.

**Response:** `List[dict]` — each dict contains relation properties (`src_id`, `tgt_id`, `description`, `keywords`, `weight`, `source_id`, etc.). The `content_vector` field is stripped from responses.

## Workspace Management

### GET /api/workspaces

List all available workspaces on the server.

**Response:**
```json
{
  "workspaces": ["pinpianyi_default", "loomgraph_demo"]
}
```

## Additional Graph CRUD Endpoints

These endpoints operate on the graph layer. All support workspace routing.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/graph/entities/merge` | POST | Merge duplicate entities |
| `/graph/entity/edit` | POST | Edit entity properties |
| `/graph/relation/edit` | POST | Edit relation properties |
| `/graph/entity/exists` | GET | Check if entity exists |

## Endpoint Origin Map

Fork-added endpoints vs upstream LightRAG:

| Endpoint | Origin | Writes To | Workspace Routing |
|----------|--------|-----------|:-:|
| `DELETE /graph/clear` | Fork | All layers | Yes |
| `DELETE /graph/by_source` | Fork | All layers | Yes |
| `POST /documents/insert_custom_kg` | Fork | All layers (graph + vector + KV) | Yes |
| `POST /graph/entity/create` | Fork | Graph + entity vector | Yes |
| `POST /graph/relation/create` | Fork | Graph + relation vector | Yes |
| `GET /graph/entities/all` | Fork | (read) Graph | Yes |
| `GET /graph/relations/all` | Fork | (read) Graph | Yes |
| `POST /graph/entities/merge` | Fork | Graph | Yes |
| `GET /api/workspaces` | Fork | N/A | N/A |
| All other `/graph/*` endpoints | Upstream | Graph | Yes (patched) |
| All other `/documents/*` endpoints | Upstream | Document | No |

## Performance Reference

| Injection Method | Entities | Relations | Time | API Calls |
|---|---|---|---|---|
| `entity/create` × N + `relation/create` × N | 586 | 952 | ~350s | ~1538 |
| `insert_custom_kg` × 1 (verified) | 3 | 2 | 0.55s | 1 |

> LoomGraph v0.2.x 使用 graph CRUD 路径。计划迁移到 `insert_custom_kg` 以获得 ~636x 性能提升 + 语义搜索能力。迁移依赖 `/graph/by_source` 端点完成增量更新支持。
