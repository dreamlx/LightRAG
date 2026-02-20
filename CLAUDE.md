# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LightRAG is a Retrieval-Augmented Generation (RAG) framework that uses graph-based knowledge representation for enhanced information retrieval. The system extracts entities and relationships from documents, builds a knowledge graph, and uses multi-modal retrieval (local, global, hybrid, mix, naive) for queries.

This is a fork of [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) with custom extensions for the code knowledge graph ecosystem.

## Ecosystem (Three-Repo Architecture)

| Repo | Role | GitHub |
|------|------|--------|
| **codeindex** | AST parsing, code structure extraction | https://github.com/dreamlx/codeindex |
| **LoomGraph** | Orchestration, data mapping, CLI/MCP entry point | https://github.com/dreamlx/LoomGraph |
| **LightRAG** | Storage, retrieval, knowledge graph management | https://github.com/dreamlx/LightRAG |

Data flow: `codeindex scan` → ParseResult → `LoomGraph embed/inject` → LightRAG API → PostgreSQL (pgvector + AGE)

Architecture details: [LoomGraph SYSTEM_DESIGN.md](https://github.com/dreamlx/LoomGraph/blob/main/docs/architecture/SYSTEM_DESIGN.md)

### Production Deployment

- Storage backend: PostgreSQL 16 (pgvector + Apache AGE) per customer (ADR-004)
- Deployment details: `docs/deployment/OPERATIONS_MANUAL.md`
- Migration roadmap: `docs/roadmap/EPIC-002-POSTGRESQL-MIGRATION.md`
- LoomGraph integration API: `docs/features/LOOMGRAPH_API.md`
- Incremental update roadmap: `docs/roadmap/EPIC-003-INCREMENTAL-UPDATE.md`

## Core Architecture

### Key Components

- **lightrag/lightrag.py**: Main orchestrator class (`LightRAG`) that coordinates document insertion, query processing, and storage management. Critical: Always call `await rag.initialize_storages()` after instantiation.

- **lightrag/operate.py**: Core extraction and query operations including entity/relation extraction, chunking, and multi-mode retrieval logic.

- **lightrag/base.py**: Abstract base classes for storage backends (`BaseKVStorage`, `BaseVectorStorage`, `BaseGraphStorage`, `BaseDocStatusStorage`).

- **lightrag/kg/**: Storage implementations (JSON, NetworkX, Neo4j, PostgreSQL, MongoDB, Redis, Milvus, Qdrant, Faiss, Memgraph). Each storage type provides different trade-offs for production vs. development use.

- **lightrag/llm/**: LLM provider bindings (OpenAI, Ollama, Azure, Gemini, Bedrock, Anthropic, etc.). All use async patterns with caching support.

- **lightrag/api/**: FastAPI server (`lightrag_server.py`) with REST endpoints and Ollama-compatible API, plus React 19 + TypeScript WebUI.

### Storage Layer

LightRAG uses 4 storage types with pluggable backends:
- **KV_STORAGE**: LLM response cache, text chunks, document info
- **VECTOR_STORAGE**: Entity/relation/chunk embeddings
- **GRAPH_STORAGE**: Entity-relation graph structure
- **DOC_STATUS_STORAGE**: Document processing status tracking

Workspace isolation is implemented differently per storage type (subdirectories for file-based, prefixes for collections, fields for relational DBs).

### Query Modes

- **local**: Context-dependent retrieval focused on specific entities
- **global**: Community/summary-based broad knowledge retrieval
- **hybrid**: Combines local and global
- **naive**: Direct vector search without graph
- **mix**: Integrates KG and vector retrieval (recommended with reranker)

## Development Commands

### Setup
```bash
# Install core package (development mode)
uv sync
source .venv/bin/activate  # Or: .venv\Scripts\activate on Windows

# Install with API support
uv sync --extra api

# Install specific extras
uv sync --extra offline-storage  # Storage backends
uv sync --extra offline-llm      # LLM providers
uv sync --extra test             # Testing dependencies
```

### API Server
```bash
# Copy and configure environment
cp env.example .env  # Edit with your LLM/embedding configs

# Build WebUI
cd lightrag_webui
bun install --frozen-lockfile
bun run build
cd ..

# Run server
lightrag-server                                           # Production
uvicorn lightrag.api.lightrag_server:app --reload        # Development
lightrag-gunicorn                                         # Multi-worker (gunicorn)
```

### Testing
```bash
# Run offline tests (default, ~3 seconds for 21 tests)
python -m pytest tests

# Run integration tests (requires external services)
python -m pytest tests --run-integration
# Or set: LIGHTRAG_RUN_INTEGRATION=true

# Run specific test file
python test_graph_storage.py

# Keep artifacts for debugging
python -m pytest tests --keep-artifacts

# Stress testing with custom workers
python -m pytest tests --stress-test --test-workers 4
```

### Linting
```bash
ruff check .
ruff check . --fix   # Auto-fix issues
ruff format .        # Format code
```

### Console Scripts (Entry Points)
```bash
lightrag-server              # Main API server
lightrag-gunicorn            # Multi-worker production server
lightrag-download-cache      # Pre-download embedding cache for offline use
lightrag-clean-llmqc         # Clean LLM query cache
```

### Docker
```bash
cp env.example .env          # Configure LLM/embedding settings
docker compose up            # Run with Docker Compose
```

## Key Implementation Patterns

### LightRAG Initialization (Critical)

The most common error is forgetting to initialize storages:

```python
import asyncio
from lightrag import LightRAG
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

async def main():
    rag = LightRAG(
        working_dir="./rag_storage",
        llm_model_func=gpt_4o_mini_complete,
        embedding_func=openai_embed
    )

    # REQUIRED: Initialize storage backends
    await rag.initialize_storages()

    # Now safe to use
    await rag.ainsert("Your text here")
    result = await rag.aquery("Your question", param=QueryParam(mode="hybrid"))

    # Cleanup
    await rag.finalize_storages()

asyncio.run(main())
```

### Custom Embedding Functions

Use `@wrap_embedding_func_with_attrs` decorator and call `.func` when wrapping:

```python
from lightrag.utils import wrap_embedding_func_with_attrs

@wrap_embedding_func_with_attrs(embedding_dim=1536, max_token_size=8192)
async def custom_embed(texts: list[str]) -> np.ndarray:
    # Call underlying function, not wrapped version
    return await openai_embed.func(texts, model="text-embedding-3-large")
```

### Storage Configuration

Configure via environment variables (recommended) or constructor params. See `env.example` for full list.

```python
rag = LightRAG(
    working_dir="./storage",
    workspace="project_name",  # For data isolation
    kv_storage="PGKVStorage",
    vector_storage="PGVectorStorage",
    graph_storage="PGGraphStorage",        # Requires Apache AGE extension
    doc_status_storage="PGDocStatusStorage",
    vector_db_storage_cls_kwargs={
        "cosine_better_than_threshold": 0.2
    }
)
```

Environment variable equivalents (used in production `.env` files):
```bash
LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_GRAPH_STORAGE=PGGraphStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage
```

### Document Insertion & Query

Standard usage — see upstream README for full examples:
```python
await rag.ainsert("Text content")                           # Single doc
await rag.ainsert(["Text 1", "Text 2"], ids=["id1", "id2"]) # Batch with IDs
result = await rag.aquery("question", param=QueryParam(mode="hybrid"))
```

### Custom API Endpoints (Fork-Specific)

These endpoints are added in our fork for LoomGraph integration:

| Endpoint | Method | Purpose | Router |
|----------|--------|---------|--------|
| `/insert_custom_kg` | POST | Inject pre-built KG (skip LLM extraction) | document_routes |
| `/api/workspaces` | GET | List available workspaces | lightrag_server |
| `/graph/entities/all` | GET | Export all entities | graph_routes |
| `/graph/relations/all` | GET | Export all relations | graph_routes |
| `/graph/entity/create` | POST | Create single entity | graph_routes |
| `/graph/relation/create` | POST | Create single relation | graph_routes |
| `/graph/entities/merge` | POST | Merge duplicate entities | graph_routes |
| `/documents/delete_entity` | DELETE | Delete entity and its relations | document_routes |

Key endpoint for LoomGraph integration:
```bash
# insert_custom_kg — bypasses LLM, directly injects entities/relations/chunks
curl -X POST /insert_custom_kg -H "Content-Type: application/json" \
  -d '{"custom_kg": {"entities": [...], "relationships": [...], "chunks": [...]}}'
```

## WebUI Development

**CRITICAL: Always use Bun** - Never use npm or yarn unless Bun is unavailable.

### Structure
- `lightrag_webui/src/`: React components (TypeScript)
- Uses Vite + Bun build system
- Tailwind CSS for styling
- React 19 with functional components and hooks
- Zustand for state management
- i18next for internationalization
- Sigma.js for graph visualization

### Commands
```bash
cd lightrag_webui
bun install --frozen-lockfile  # Install dependencies
bun run dev                    # Development server (localhost:5173)
bun run build                  # Production build
bun run lint                   # ESLint checks
bun test                       # Run tests
bun run preview                # Preview production build
```

## Common Issues

### 1. Storage Not Initialized
**Error**: `AttributeError: __aenter__` or `KeyError: 'history_messages'`
**Solution**: Always call `await rag.initialize_storages()` after creating LightRAG instance

### 2. Embedding Model Changes
When switching embedding models, you MUST clear the data directory (except optionally `kv_store_llm_response_cache.json` for LLM cache).

### 3. Nested Embedding Functions
Cannot wrap already-decorated embedding functions. Use `.func` to access underlying function:
```python
# Wrong: EmbeddingFunc(func=openai_embed)
# Right: EmbeddingFunc(func=openai_embed.func)
```

### 4. Context Length for Ollama
Ollama models default to 8k context; LightRAG requires 32k+. Set `llm_model_kwargs={"options": {"num_ctx": 32768}}`.

### 5. PGGraphStorage Requires Apache AGE
`PGGraphStorage` depends on the Apache AGE extension. Use a Docker image that includes it (e.g., `marcosbolanos/pgvector-age`). Plain `pgvector/pgvector` will fail with `function create_graph(unknown) does not exist`.

### 6. Async Generator Lock Management
Never hold locks across async generator yields - create snapshots instead to prevent deadlocks:
```python
# WRONG - Deadlock prone:
async with storage._storage_lock:
    for key, value in storage._data.items():
        yield batch  # Lock still held!

# CORRECT - Snapshot approach:
async with storage._storage_lock:
    matching_items = list(storage._data.items())
# Lock released here
for key, value in matching_items:
    yield batch  # No lock held
```

### 7. Lock Key Generation for Relationships
Always sort relationship pairs for consistent lock keys to prevent deadlocks:
```python
sorted_key_parts = sorted([src, tgt])
lock_key = f"{sorted_key_parts[0]}-{sorted_key_parts[1]}"
```

## Configuration Files

### .env Configuration
Primary configuration file for API server. Key sections:
- Server settings (HOST, PORT, CORS)
- Storage backends (connection strings via environment variables)
- Query parameters (TOP_K, MAX_TOTAL_TOKENS, etc.)
- Reranking configuration (RERANK_BINDING, RERANK_MODEL)
- Authentication (AUTH_ACCOUNTS, LIGHTRAG_API_KEY)

See `env.example` for comprehensive template.

### Workspace Isolation
Each LightRAG instance can use a `workspace` parameter for data isolation. Implementation varies by storage type:
- File-based: subdirectories
- Collection-based: collection name prefixes
- Relational DB: workspace column filtering
- Qdrant: payload-based partitioning

## Testing Guidelines

### Test Structure
- `tests/`: Main test suite with `conftest.py` for fixtures and custom options
- `test_*.py` in root: Specific integration tests
- Markers: `offline` (CI default), `integration`, `requires_db`, `requires_api`

### Environment Variables for Tests
- `LIGHTRAG_RUN_INTEGRATION=true` - Enable integration tests
- `LIGHTRAG_KEEP_ARTIFACTS=true` - Preserve temp files for debugging
- `LIGHTRAG_STRESS_TEST=true` - Enable intensive workloads
- `LIGHTRAG_TEST_WORKERS=N` - Parallel worker count
- Storage-specific connection strings for integration tests

## Code Style

### Language
- Comment Language - Use English for comments and documentation
- Backend Language - Use English for backend code and messages
- Frontend Internationalization: i18next for multi-language support

### Python
- Follow PEP 8 with 4-space indentation
- Use type annotations
- Prefer dataclasses for state management
- Use `lightrag.utils.logger` instead of print
- Async/await patterns throughout
- Keep storage implementations in `kg/` with consistent base class inheritance

### TypeScript/React
- Functional components with hooks
- 2-space indentation
- PascalCase for components
- Tailwind utility-first styling

## Important Architectural Notes

### LLM Requirements
- Minimum 32B parameters recommended
- 32KB context minimum (64KB recommended)
- Avoid reasoning models during indexing
- Stronger models for query stage than indexing stage

### Embedding Models
- Must be consistent across indexing and querying
- Production (code analysis): `jinaai/jina-embeddings-v2-base-code` (768d, 8K context) via TEI
- General purpose: `BAAI/bge-m3`, `text-embedding-3-large`
- Changing models requires clearing vector storage and Cold Rebuild with new dimensions

### Reranker Configuration
- Significantly improves retrieval quality
- Recommended models: `BAAI/bge-reranker-v2-m3`, Jina rerankers
- Use "mix" mode when reranker is enabled
