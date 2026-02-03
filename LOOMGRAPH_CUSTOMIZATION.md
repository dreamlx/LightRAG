# LightRAG 定制任务清单 (LoomGraph 集成)

**分支**: `loomgraph-main`
**目标**: 让 LightRAG 直接摄入 codeindex 产出的 AST 数据，跳过内置 Chunking 和 LLM 实体提取

---

## 发现：LightRAG 已有关键接口

### 现有 API

| 方法 | 功能 | 我们的使用方式 |
|------|------|----------------|
| `ainsert()` | 完整流程（chunking + LLM 提取） | 不使用 |
| `ainsert_custom_chunks()` | 自定义 chunks（仍需 LLM 提取） | 可选 |
| `ainsert_custom_kg()` | **直接插入图谱（跳过 LLM）** | ✅ 主要使用 |

### `ainsert_custom_kg` 数据格式

```python
custom_kg = {
    "chunks": [
        {
            "content": "def login(username, password): ...",
            "source_id": "user_service.py:42",
            "file_path": "src/services/user_service.py",
            "chunk_order_index": 0
        }
    ],
    "entities": [
        {
            "entity_name": "UserService.login",
            "entity_type": "method",
            "description": "用户登录验证方法",
            "source_id": "user_service.py:42",
            "file_path": "src/services/user_service.py"
        }
    ],
    "relationships": [
        {
            "src_id": "UserService.login",
            "tgt_id": "hashlib.sha256",
            "description": "UserService.login 调用 hashlib.sha256 进行密码哈希",
            "keywords": "calls,dependency",
            "weight": 1.0,
            "source_id": "user_service.py:42"
        }
    ]
}

await rag.ainsert_custom_kg(custom_kg)
```

---

## 任务清单

### Epic 1: codeindex 适配器 (在 LoomGraph 中实现)

> 这部分代码应该在 LoomGraph 项目中，将 codeindex 的 ParseResult 转换为 LightRAG 格式

```python
# loomgraph/adapters/codeindex_to_lightrag.py

from codeindex.parser import ParseResult, Symbol, Import, Call, Inheritance

def parse_result_to_custom_kg(
    parse_result: ParseResult,
    include_llm_enhancement: bool = False
) -> dict:
    """
    将 codeindex 的 ParseResult 转换为 LightRAG custom_kg 格式
    """
    chunks = []
    entities = []
    relationships = []

    # 1. 转换 Symbols 为 Chunks + Entities
    for symbol in parse_result.symbols:
        source_id = f"{parse_result.path}:{symbol.line_start}"

        # Chunk
        chunks.append({
            "content": symbol.signature + "\n" + symbol.docstring,
            "source_id": source_id,
            "file_path": str(parse_result.path),
        })

        # Entity
        entities.append({
            "entity_name": symbol.name,
            "entity_type": symbol.kind,
            "description": symbol.docstring or symbol.signature,
            "source_id": source_id,
        })

    # 2. 转换 Imports 为 Relationships
    for imp in parse_result.imports:
        relationships.append({
            "src_id": parse_result.path.stem,  # 模块名
            "tgt_id": imp.module,
            "description": f"imports {imp.module}",
            "keywords": "imports,dependency",
            "weight": 1.0,
        })

    # 3. 转换 Calls 为 Relationships (需要 codeindex 扩展)
    for call in getattr(parse_result, 'calls', []):
        relationships.append({
            "src_id": call.caller,
            "tgt_id": call.callee,
            "description": f"{call.caller} calls {call.callee}",
            "keywords": "calls,invocation",
            "weight": 1.0,
        })

    # 4. 转换 Inheritances 为 Relationships (需要 codeindex 扩展)
    for inherit in getattr(parse_result, 'inheritances', []):
        relationships.append({
            "src_id": inherit.child,
            "tgt_id": inherit.parent,
            "description": f"{inherit.child} extends {inherit.parent}",
            "keywords": "inherits,extends",
            "weight": 1.0,
        })

    return {
        "chunks": chunks,
        "entities": entities,
        "relationships": relationships,
    }
```

**状态**: 📋 待实现 (在 LoomGraph 中)

---

### Epic 2: LightRAG PostgreSQL 配置优化 (可选)

LightRAG 已有 `postgres_impl.py`，但可能需要优化：

#### Task 2.1: 验证现有 PostgreSQL 存储

```bash
# 测试现有 PostgreSQL 存储是否满足需求
cd /Users/dreamlinx/Projects/LightRAG
pytest tests/ -k postgres -v
```

**检查点**:
- [ ] pgvector 索引类型配置（HNSW vs IVFFlat）
- [ ] 连接池配置是否适合高并发
- [ ] 是否支持批量 upsert

#### Task 2.2: 添加代码专用字段（如需要）

如果需要在 entities/relationships 表中添加代码专用字段：

```sql
-- 可能需要的字段
ALTER TABLE entities ADD COLUMN IF NOT EXISTS
    symbol_kind VARCHAR(50);  -- function, class, method, etc.

ALTER TABLE relationships ADD COLUMN IF NOT EXISTS
    relation_type VARCHAR(50);  -- calls, imports, inherits, uses
```

**状态**: 📋 待验证

---

### Epic 3: 代码专用 Prompt 模板 (可选 - 仅当需要 LLM 语义增强时)

如果选择让 LLM 补充语义描述，需要定制 prompts：

#### Task 3.1: 创建代码专用实体提取 prompt

文件: `lightrag/prompt.py` 新增

```python
PROMPTS["code_entity_extraction"] = """
You are analyzing source code. Extract entities and relationships.

Entity types for code:
- function: A standalone function
- method: A method inside a class
- class: A class definition
- module: A module/file
- variable: Important variables/constants

Relationship types for code:
- calls: Function/method invocation
- imports: Module import
- inherits: Class inheritance
- uses: Variable/constant usage

Code:
{input_text}

Output format: ...
"""
```

**状态**: 📋 待定（取决于是否需要 LLM 增强）

---

### Epic 4: 集成测试

#### Task 4.1: 创建 codeindex → LightRAG 集成测试

```python
# tests/test_codeindex_integration.py

import pytest
from lightrag import LightRAG

@pytest.mark.asyncio
async def test_insert_custom_kg_from_codeindex():
    """测试从 codeindex 格式直接插入图谱"""

    rag = LightRAG(
        working_dir="./test_rag",
        kv_storage="PostgresKVStorage",
        vector_storage="PGVectorStorage",
        graph_storage="PostgresStorage",
    )

    # Mock codeindex 数据
    custom_kg = {
        "chunks": [...],
        "entities": [...],
        "relationships": [...],
    }

    await rag.ainsert_custom_kg(custom_kg)

    # 验证查询
    result = await rag.aquery("What does UserService.login do?")
    assert "login" in result.lower()
```

**状态**: 📋 待实现

---

## 优先级排序

| 优先级 | 任务 | 位置 | 说明 |
|--------|------|------|------|
| **P0** | Epic 1: codeindex 适配器 | LoomGraph | 核心转换逻辑 |
| **P1** | Task 2.1: 验证 PostgreSQL 存储 | LightRAG | 确认现有实现是否满足需求 |
| **P2** | Epic 4: 集成测试 | LightRAG | 端到端验证 |
| **P3** | Epic 3: 代码 Prompts | LightRAG | 仅当需要 LLM 增强时 |

---

## 快速开始命令

```bash
# 1. 切换到 loomgraph-main 分支
cd /Users/dreamlinx/Projects/LightRAG
git checkout loomgraph-main

# 2. 创建测试环境
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. 启动 PostgreSQL (使用 LoomGraph 的 docker-compose)
cd /Users/dreamlinx/Dropbox/Projects/NetBeansProjects/LoomGraph
docker compose up -d postgres

# 4. 运行现有测试
cd /Users/dreamlinx/Projects/LightRAG
pytest tests/ -v

# 5. 验证 PostgreSQL 存储
pytest tests/ -k "postgres" -v
```

---

## 结论

**好消息**: LightRAG 已有 `ainsert_custom_kg()` 接口，可以直接插入预处理好的图谱数据，**不需要大规模修改 LightRAG**。

**主要工作**:
1. **LoomGraph 侧**: 实现 codeindex → LightRAG 适配器
2. **LightRAG 侧**: 验证 PostgreSQL 存储 + 编写集成测试
3. **可选**: 代码专用 prompts（如需要 LLM 语义增强）

**预期定制量**: 低 (主要是测试和验证)
