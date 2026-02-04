# LoomGraph 集成指南

本文档说明如何使用 LightRAG API 进行代码索引场景的集成。

## 快速开始

```python
import asyncio
from lightrag import LightRAG, QueryParam

async def main():
    rag = LightRAG(working_dir="./code_index")
    await rag.initialize_storages()

    # 创建代码实体
    await rag.acreate_entity(
        entity_name="auth.login",
        entity_data={
            "entity_type": "method",
            "description": "def login(username, password) -> bool | Authenticate user | Python",
            "source_id": "src/auth.py:12-25",
            "file_path": "src/auth.py",
        }
    )

    # 创建调用关系
    await rag.acreate_relation(
        source_entity="auth.login",
        target_entity="db.query_user",
        relation_data={
            "keywords": "CALLS",
            "description": "login calls query_user",
            "weight": 1.0,
        }
    )

    await rag.finalize_storages()

asyncio.run(main())
```

## API 参考

### acreate_entity()

创建代码实体（类、方法、函数、模块等）。

```python
result = await rag.acreate_entity(
    entity_name: str,      # 实体唯一标识，如 "auth.AuthService.login"
    entity_data: dict      # 实体属性
)
```

**entity_data 字段:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `entity_type` | str | 是 | 实体类型: method, class, function, module, variable |
| `description` | str | 是 | 描述信息，建议包含 signature、language 等 |
| `source_id` | str | 否 | 来源标识，如 "src/auth.py:12-25" |
| `file_path` | str | 否 | 文件路径 |

**返回结构:**

```python
{
    "entity_name": "auth.login",
    "graph_data": {
        "entity_type": "method",
        "description": "...",
        "source_id": "...",
        "created_at": 1234567890
    },
    "vector_data": {...}
}
```

**注意:**
- 如果实体已存在，会抛出 `ValueError`
- embedding 由 LightRAG 自动生成，不支持外部传入

---

### acreate_relation()

创建代码关系（调用、继承、导入等）。

```python
result = await rag.acreate_relation(
    source_entity: str,    # 源实体名称
    target_entity: str,    # 目标实体名称
    relation_data: dict    # 关系属性
)
```

**relation_data 字段:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keywords` | str | 是 | **关系类型**: CALLS, INHERITS, IMPORTS, IMPLEMENTS, CONTAINS |
| `description` | str | 否 | 关系描述 |
| `weight` | float | 否 | 权重，默认 1.0 |
| `source_id` | str | 否 | 来源标识，如 "src/auth.py:15" |

**注意:**
- 源和目标实体必须先存在，否则抛出 `ValueError`
- 如果关系已存在，会抛出 `ValueError`
- 使用 `keywords` 字段存储关系类型（CALLS, INHERITS 等）

---

### adelete_by_entity()

删除实体及其关联的所有关系（级联删除）。

```python
result = await rag.adelete_by_entity(entity_name: str)
```

**行为:**
- 删除指定实体
- 自动删除所有关联的 relations
- 从向量库中移除对应记录

---

### 图遍历 API

```python
# 检查节点是否存在
exists = await rag.chunk_entity_relation_graph.has_node(entity_name)

# 获取节点的所有边
edges = await rag.chunk_entity_relation_graph.get_node_edges(entity_name)
# 返回: list[tuple[str, str]] 或 None
```

---

## 字段映射约定

将代码解析结果映射到 LightRAG 字段：

| 代码属性 | LightRAG 字段 | 格式示例 |
|----------|---------------|----------|
| 实体类型 | `entity_type` | "method", "class" |
| 函数签名 | `description` | 拼接到 description |
| 语言 | `description` | 拼接到 description |
| 文档字符串 | `description` | 拼接到 description |
| 文件路径 | `file_path` | "src/auth.py" |
| 行号范围 | `source_id` | "src/auth.py:12-25" |
| 关系类型 | `keywords` | "CALLS", "INHERITS" |
| embedding | **不传** | LightRAG 自动生成 |

**description 拼接示例:**

```python
description = f"{signature} | {docstring} | {language}"
# 例: "def login(username, password) -> bool | Authenticate user | Python"
```

---

## 全量重建

MVP 阶段推荐使用全量重建策略：

```python
import shutil

async def rebuild_index(repo_path: str, rag: LightRAG):
    # 1. 关闭当前存储
    await rag.finalize_storages()

    # 2. 清空数据目录
    shutil.rmtree(rag.working_dir, ignore_errors=True)

    # 3. 重新初始化（会创建新的空存储）
    await rag.initialize_storages()

    # 4. 重新注入数据
    for file_path in scan_code_files(repo_path):
        result = parse_file(file_path)
        await inject_entities_and_relations(rag, result)
```

**注意:** 必须创建新的 LightRAG 实例或重新 `initialize_storages()`，因为内存中的图存储会保留旧数据。

---

## 示例代码

完整示例见: `examples/loomgraph_integration_demo.py`

---

## 测试

```bash
# 运行集成测试
pytest tests/test_loomgraph_integration.py -v
```

---

## 相关文档

- [LoomGraph 需求文档](https://github.com/user/LoomGraph/docs/integration/LIGHTRAG_REQUIREMENTS.md)
- [更新策略](https://github.com/user/LoomGraph/docs/architecture/UPDATE_STRATEGY.md)
