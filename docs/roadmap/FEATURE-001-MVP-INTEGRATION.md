# Feature 1: LoomGraph MVP 集成验证

**Feature ID**: FEATURE-001
**Epic**: EPIC-001 (LoomGraph 集成支持)
**版本**: v1.5.0
**状态**: ✅ 已完成

---

## 目标

验证 LightRAG 现有 API 满足 LoomGraph 代码索引集成需求，并提供示例代码和测试用例。

---

## Story 列表

### S1.1 编写 LoomGraph 集成示例代码

**估点**: 2
**状态**: ✅ 已完成

#### 验收标准

- [ ] 创建 `examples/loomgraph_integration_demo.py`
- [ ] 演示 entity 创建 (method, class, function)
- [ ] 演示 relation 创建 (CALLS, INHERITS, IMPORTS)
- [ ] 演示语义查询
- [ ] 演示图遍历
- [ ] 演示全量重建流程

#### 示例代码框架

```python
# examples/loomgraph_integration_demo.py
"""
LoomGraph 集成示例 - 代码索引场景

演示如何使用 LightRAG API 存储和检索代码结构信息。
"""

import asyncio
import shutil
from lightrag import LightRAG, QueryParam


async def main():
    # 1. 初始化
    rag = LightRAG(working_dir="./loomgraph_demo")
    await rag.initialize_storages()

    # 2. 创建代码 Entities
    await create_code_entities(rag)

    # 3. 创建代码 Relations
    await create_code_relations(rag)

    # 4. 语义搜索
    await demo_semantic_search(rag)

    # 5. 图遍历
    await demo_graph_traversal(rag)

    # 6. 全量重建
    await demo_full_rebuild(rag)

    await rag.finalize_storages()


async def create_code_entities(rag: LightRAG):
    """演示创建代码实体."""
    # Method entity
    await rag.acreate_entity(
        entity_name="auth.login",
        entity_data={
            "entity_type": "method",
            "description": "def login(username: str, password: str) -> bool | Authenticate user credentials | Python",
            "source_id": "src/auth.py:12-25",
            "file_path": "src/auth.py",
        }
    )
    # ... more entities


async def create_code_relations(rag: LightRAG):
    """演示创建代码关系."""
    await rag.acreate_relation(
        source_entity="auth.login",
        target_entity="db.query_user",
        relation_data={
            "keywords": "CALLS",
            "description": "auth.login calls db.query_user to verify credentials",
            "weight": 1.0,
            "source_id": "src/auth.py:15",
        }
    )
    # ... more relations


if __name__ == "__main__":
    asyncio.run(main())
```

---

### S1.2 编写集成测试用例

**估点**: 3
**状态**: ✅ 已完成 (20/20 tests passed)

#### TDD 测试设计

```python
# tests/test_loomgraph_integration.py
"""
LoomGraph 集成测试 - TDD 先行

测试 LightRAG API 是否满足代码索引场景需求。
"""

import pytest
from lightrag import LightRAG, QueryParam


@pytest.fixture
async def rag_instance(tmp_path):
    """创建临时 LightRAG 实例."""
    rag = LightRAG(
        working_dir=str(tmp_path / "rag_storage"),
        llm_model_func=mock_llm_func,
        embedding_func=mock_embedding_func,
    )
    await rag.initialize_storages()
    yield rag
    await rag.finalize_storages()


class TestEntityCreation:
    """测试 Entity 创建功能."""

    @pytest.mark.offline
    async def test_create_method_entity(self, rag_instance):
        """测试创建 method 类型的 entity."""
        result = await rag_instance.acreate_entity(
            entity_name="auth.login",
            entity_data={
                "entity_type": "method",
                "description": "def login(username, password) -> bool",
                "source_id": "src/auth.py:12-25",
                "file_path": "src/auth.py",
            }
        )

        assert result is not None
        assert result["entity_name"] == "auth.login"
        assert "entity_type" in result

    @pytest.mark.offline
    async def test_create_duplicate_entity_raises_error(self, rag_instance):
        """测试创建重复 entity 应该抛错."""
        await rag_instance.acreate_entity(
            entity_name="auth.login",
            entity_data={"entity_type": "method", "description": "test"}
        )

        with pytest.raises(ValueError, match="already exists"):
            await rag_instance.acreate_entity(
                entity_name="auth.login",
                entity_data={"entity_type": "method", "description": "duplicate"}
            )

    @pytest.mark.offline
    async def test_entity_type_mapping(self, rag_instance):
        """测试各种代码实体类型的映射."""
        entity_types = ["method", "class", "function", "module", "variable"]

        for entity_type in entity_types:
            result = await rag_instance.acreate_entity(
                entity_name=f"test.{entity_type}_example",
                entity_data={
                    "entity_type": entity_type,
                    "description": f"Test {entity_type}",
                    "source_id": f"src/test.py:1",
                    "file_path": "src/test.py",
                }
            )
            assert result["entity_type"] == entity_type


class TestRelationCreation:
    """测试 Relation 创建功能."""

    @pytest.mark.offline
    async def test_create_calls_relation(self, rag_instance):
        """测试创建 CALLS 类型的 relation."""
        # 先创建两个 entities
        await rag_instance.acreate_entity(
            entity_name="caller",
            entity_data={"entity_type": "method", "description": "caller"}
        )
        await rag_instance.acreate_entity(
            entity_name="callee",
            entity_data={"entity_type": "method", "description": "callee"}
        )

        # 创建 relation
        result = await rag_instance.acreate_relation(
            source_entity="caller",
            target_entity="callee",
            relation_data={
                "keywords": "CALLS",
                "description": "caller invokes callee",
                "weight": 1.0,
            }
        )

        assert result is not None
        assert "CALLS" in str(result)

    @pytest.mark.offline
    async def test_relation_types_via_keywords(self, rag_instance):
        """测试通过 keywords 字段存储 relation_type."""
        relation_types = ["CALLS", "INHERITS", "IMPORTS", "IMPLEMENTS"]

        for i, rel_type in enumerate(relation_types):
            # 创建源和目标 entities
            src = f"src_{i}"
            tgt = f"tgt_{i}"
            await rag_instance.acreate_entity(src, {"entity_type": "class", "description": src})
            await rag_instance.acreate_entity(tgt, {"entity_type": "class", "description": tgt})

            # 创建 relation
            result = await rag_instance.acreate_relation(
                source_entity=src,
                target_entity=tgt,
                relation_data={"keywords": rel_type, "description": f"{src} {rel_type} {tgt}"}
            )

            assert rel_type in str(result)

    @pytest.mark.offline
    async def test_create_relation_nonexistent_entity_raises_error(self, rag_instance):
        """测试创建关系时引用不存在的 entity 应该抛错."""
        with pytest.raises(ValueError, match="does not exist"):
            await rag_instance.acreate_relation(
                source_entity="nonexistent",
                target_entity="also_nonexistent",
                relation_data={"keywords": "CALLS", "description": "test"}
            )


class TestGraphTraversal:
    """测试图遍历功能."""

    @pytest.mark.offline
    async def test_get_node_edges(self, rag_instance):
        """测试获取节点的所有边."""
        # Setup: 创建一个中心节点和多个关联节点
        await rag_instance.acreate_entity("center", {"entity_type": "class", "description": "center"})
        await rag_instance.acreate_entity("neighbor1", {"entity_type": "method", "description": "n1"})
        await rag_instance.acreate_entity("neighbor2", {"entity_type": "method", "description": "n2"})

        await rag_instance.acreate_relation("center", "neighbor1", {"keywords": "CALLS", "description": "c1"})
        await rag_instance.acreate_relation("center", "neighbor2", {"keywords": "CALLS", "description": "c2"})

        # Test
        edges = await rag_instance.chunk_entity_relation_graph.get_node_edges("center")

        assert edges is not None
        assert len(edges) == 2


class TestDeletion:
    """测试删除功能."""

    @pytest.mark.offline
    async def test_delete_entity_cascades_relations(self, rag_instance):
        """测试删除 entity 时自动删除关联的 relations."""
        # Setup
        await rag_instance.acreate_entity("to_delete", {"entity_type": "class", "description": "del"})
        await rag_instance.acreate_entity("related", {"entity_type": "method", "description": "rel"})
        await rag_instance.acreate_relation("to_delete", "related", {"keywords": "CALLS", "description": "r"})

        # Delete
        result = await rag_instance.adelete_by_entity("to_delete")

        # Verify entity is gone
        has_node = await rag_instance.chunk_entity_relation_graph.has_node("to_delete")
        assert has_node is False

        # Verify relation is also gone
        edges = await rag_instance.chunk_entity_relation_graph.get_node_edges("related")
        assert edges is None or len(edges) == 0


class TestFullRebuild:
    """测试全量重建场景."""

    @pytest.mark.offline
    async def test_clear_and_rebuild(self, rag_instance, tmp_path):
        """测试清空后重建."""
        import shutil

        # Setup: 创建一些数据
        await rag_instance.acreate_entity("old_entity", {"entity_type": "class", "description": "old"})

        # Clear
        await rag_instance.finalize_storages()
        shutil.rmtree(rag_instance.working_dir, ignore_errors=True)
        await rag_instance.initialize_storages()

        # Verify old data is gone
        has_old = await rag_instance.chunk_entity_relation_graph.has_node("old_entity")
        assert has_old is False

        # Rebuild with new data
        await rag_instance.acreate_entity("new_entity", {"entity_type": "class", "description": "new"})
        has_new = await rag_instance.chunk_entity_relation_graph.has_node("new_entity")
        assert has_new is True
```

#### 验收标准

- [ ] 所有测试用例通过
- [ ] 测试覆盖率 > 90%
- [ ] 使用 `@pytest.mark.offline` 标记，可在 CI 中运行

---

### S1.3 更新 API 文档说明

**估点**: 1
**状态**: 🔲 待开始

#### 验收标准

- [ ] 在 `docs/api/` 中添加代码索引集成说明
- [ ] 说明字段映射约定
- [ ] 说明全量重建推荐做法

---

## 测试计划

### 单元测试

```bash
# 运行 LoomGraph 集成相关测试
pytest tests/test_loomgraph_integration.py -v

# 运行所有 offline 测试
pytest tests -m offline -v
```

### 集成测试

```bash
# 需要实际的 LLM/Embedding 服务
pytest tests/test_loomgraph_integration.py --run-integration -v
```

---

## Definition of Done

- [ ] 所有 Stories 完成
- [ ] 测试全部通过
- [ ] 代码已 review
- [ ] 文档已更新
- [ ] 示例代码可运行
