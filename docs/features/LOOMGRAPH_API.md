# LoomGraph Integration API Reference

LightRAG fork endpoints used by LoomGraph for code knowledge graph workflows.

All endpoints support workspace routing via `LIGHTRAG-WORKSPACE` header.

## Cold Rebuild Flow (ADR-003)

```bash
# 1. Clear all data for workspace
curl -X DELETE http://host:port/graph/clear \
  -H "LIGHTRAG-WORKSPACE: loomgraph_demo"

# 2. Re-inject fresh knowledge graph
curl -X POST http://host:port/documents/insert_custom_kg \
  -H "LIGHTRAG-WORKSPACE: loomgraph_demo" \
  -H "Content-Type: application/json" \
  -d '{"custom_kg": {"chunks": [...], "entities": [...], "relationships": [...]}}'

# 3. Verify (optional)
curl http://host:port/graph/entities/all \
  -H "LIGHTRAG-WORKSPACE: loomgraph_demo"
```

## Core Endpoints

### DELETE /graph/clear

Clear all storage data for a workspace. Drops all 11 storage backends in parallel. Does NOT delete `llm_response_cache` (reusable across rebuilds). Does NOT delete input directory files.

**Response:**
```json
{
  "status": "success",          // or "partial_success"
  "workspace": "loomgraph_demo",
  "storages_cleared": 11,
  "errors": null                // or ["error detail", ...]
}
```

**Error codes:**
- `409` — Pipeline is busy (indexing in progress)
- `500` — All storage drops failed

### POST /documents/insert_custom_kg

Inject pre-built knowledge graph, bypassing LLM extraction. This is the primary data ingestion path for LoomGraph.

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
        "keywords": "defines",
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

## Export Endpoints

### GET /graph/entities/all

Returns all entity nodes in the knowledge graph.

**Response:** `List[dict]` — each dict contains entity properties (`entity_name`, `entity_type`, `description`, `source_id`, etc.). The `content_vector` field is stripped from responses.

### GET /graph/relations/all

Returns all relation edges in the knowledge graph.

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

## Graph CRUD Endpoints

These endpoints are available for incremental updates (WebUI or future use). All support workspace routing.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/graph/entity/create` | POST | Create a single entity |
| `/graph/relation/create` | POST | Create a single relation |
| `/graph/entities/merge` | POST | Merge duplicate entities |
| `/graph/entity/edit` | POST | Edit entity properties |
| `/graph/relation/edit` | POST | Edit relation properties |
| `/graph/entity/exists` | GET | Check if entity exists |

## Endpoint Origin Map

Fork-added endpoints vs upstream LightRAG:

| Endpoint | Origin | Workspace Routing |
|----------|--------|:-:|
| `DELETE /graph/clear` | Fork | Yes |
| `POST /documents/insert_custom_kg` | Fork | Yes |
| `GET /graph/entities/all` | Fork | Yes |
| `GET /graph/relations/all` | Fork | Yes |
| `POST /graph/entity/create` | Fork | Yes |
| `POST /graph/relation/create` | Fork | Yes |
| `POST /graph/entities/merge` | Fork | Yes |
| `GET /api/workspaces` | Fork | N/A |
| All other `/graph/*` endpoints | Upstream | Yes (patched) |
| All other `/documents/*` endpoints | Upstream | No |
