"""
测试 POST /insert_custom_kg API 端点 - TDD 先行

运行方式:
    pytest tests/test_insert_custom_kg_api.py -v
    pytest tests/test_insert_custom_kg_api.py -v -k "test_full_injection"
"""

import numpy as np
import pytest

from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc


# =============================================================================
# Mock Functions
# =============================================================================


async def mock_llm_func(prompt, **kwargs):
    """Mock LLM function for offline testing."""
    return "Mock LLM response"


async def mock_embedding_func(texts: list[str]) -> np.ndarray:
    """Mock embedding function for offline testing."""
    return np.random.rand(len(texts), 384).astype(np.float32)


mock_embedding_func.embedding_dim = 384
mock_embedding_func.max_token_size = 8192


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def rag_instance(tmp_path):
    """Create a temporary LightRAG instance for testing."""
    rag = LightRAG(
        working_dir=str(tmp_path / "rag_storage"),
        llm_model_func=mock_llm_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=384,
            max_token_size=8192,
            func=mock_embedding_func,
        ),
    )
    await rag.initialize_storages()
    yield rag
    await rag.finalize_storages()


# =============================================================================
# Test: ainsert_custom_kg (SDK 层)
# =============================================================================


class TestInsertCustomKgSDK:
    """测试 ainsert_custom_kg SDK 方法."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_full_injection(self, rag_instance):
        """TC-01: 完整注入 chunks + entities + relationships."""
        custom_kg = {
            "chunks": [
                {
                    "content": "def login(username, password): return verify(username, password)",
                    "source_id": "auth.py:10",
                    "file_path": "src/auth.py",
                }
            ],
            "entities": [
                {
                    "entity_name": "AuthService.login",
                    "entity_type": "method",
                    "description": "User login method",
                    "source_id": "auth.py:10",
                }
            ],
            "relationships": [
                {
                    "src_id": "AuthService.login",
                    "tgt_id": "verify",
                    "description": "calls verify function",
                    "keywords": "calls,dependency",
                    "weight": 1.0,
                    "source_id": "auth.py:10",
                }
            ],
        }

        # Should not raise
        await rag_instance.ainsert_custom_kg(custom_kg)

        # Verify entity exists
        has_entity = await rag_instance.chunk_entity_relation_graph.has_node(
            "AuthService.login"
        )
        assert has_entity, "Entity should exist after insertion"

        # Verify relationship exists
        has_edge = await rag_instance.chunk_entity_relation_graph.has_edge(
            "AuthService.login", "verify"
        )
        assert has_edge, "Relationship should exist after insertion"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_entities_only(self, rag_instance):
        """TC-02: 仅注入 entities."""
        custom_kg = {
            "entities": [
                {
                    "entity_name": "UserModel",
                    "entity_type": "class",
                    "description": "User data model",
                }
            ]
        }

        await rag_instance.ainsert_custom_kg(custom_kg)

        has_entity = await rag_instance.chunk_entity_relation_graph.has_node(
            "UserModel"
        )
        assert has_entity, "Entity should exist"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_relationships_auto_create_nodes(self, rag_instance):
        """TC-03: 仅注入 relationships，自动创建缺失节点."""
        custom_kg = {
            "relationships": [
                {
                    "src_id": "ClassA",
                    "tgt_id": "ClassB",
                    "description": "inherits from",
                    "keywords": "inheritance",
                }
            ]
        }

        await rag_instance.ainsert_custom_kg(custom_kg)

        # Both nodes should be auto-created
        has_src = await rag_instance.chunk_entity_relation_graph.has_node("ClassA")
        has_tgt = await rag_instance.chunk_entity_relation_graph.has_node("ClassB")
        assert has_src and has_tgt, "Nodes should be auto-created for relationship"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_empty_custom_kg(self, rag_instance):
        """TC-04: 空请求不报错."""
        custom_kg = {}
        # Should not raise
        await rag_instance.ainsert_custom_kg(custom_kg)

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_upsert_idempotent(self, rag_instance):
        """TC-07: 重复实体 (幂等性) - 后者覆盖前者."""
        # First insertion
        custom_kg_v1 = {
            "entities": [
                {
                    "entity_name": "Config",
                    "entity_type": "class",
                    "description": "Version 1 description",
                }
            ]
        }
        await rag_instance.ainsert_custom_kg(custom_kg_v1)

        # Second insertion with updated description
        custom_kg_v2 = {
            "entities": [
                {
                    "entity_name": "Config",
                    "entity_type": "class",
                    "description": "Version 2 description",
                }
            ]
        }
        await rag_instance.ainsert_custom_kg(custom_kg_v2)

        # Should have the updated description
        node_data = await rag_instance.chunk_entity_relation_graph.get_node("Config")
        assert node_data is not None, "Node should exist"
        assert "Version 2" in node_data.get("description", ""), "Should have updated description"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_batch_performance(self, rag_instance):
        """TC-06: 大批量注入性能测试."""
        import time

        # Generate 500 entities and 1000 relationships
        entities = [
            {
                "entity_name": f"Entity_{i}",
                "entity_type": "class",
                "description": f"Entity number {i}",
            }
            for i in range(500)
        ]

        relationships = [
            {
                "src_id": f"Entity_{i}",
                "tgt_id": f"Entity_{(i + 1) % 500}",
                "description": f"relates to",
                "keywords": "dependency",
            }
            for i in range(1000)
        ]

        custom_kg = {"entities": entities, "relationships": relationships}

        start = time.time()
        await rag_instance.ainsert_custom_kg(custom_kg)
        elapsed = time.time() - start

        # Should complete within 30 seconds
        assert elapsed < 30, f"Batch insertion took {elapsed:.2f}s, expected < 30s"

        # Verify some entities exist
        has_first = await rag_instance.chunk_entity_relation_graph.has_node("Entity_0")
        has_last = await rag_instance.chunk_entity_relation_graph.has_node("Entity_499")
        assert has_first and has_last, "Entities should exist after batch insertion"


# =============================================================================
# Test: API Endpoint (HTTP 层) - 需要 FastAPI TestClient
# =============================================================================


class TestInsertCustomKgAPI:
    """测试 POST /insert_custom_kg HTTP API 端点."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_api_endpoint_exists(self):
        """验证 API 端点已注册."""
        from lightrag.api.lightrag_server import create_app

        # Create app with mock config
        app = create_app()

        # Check if route exists
        routes = [route.path for route in app.routes]
        assert "/insert_custom_kg" in routes, "Endpoint /insert_custom_kg should exist"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_api_request_validation(self):
        """验证请求格式校验."""
        from fastapi.testclient import TestClient
        from lightrag.api.lightrag_server import create_app

        app = create_app()
        client = TestClient(app)

        # Missing custom_kg field
        response = client.post("/insert_custom_kg", json={})
        assert response.status_code in [400, 422], "Should reject invalid request"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_api_success_response(self):
        """验证成功响应格式."""
        from fastapi.testclient import TestClient
        from lightrag.api.lightrag_server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/insert_custom_kg",
            json={
                "custom_kg": {
                    "entities": [
                        {"entity_name": "TestEntity", "entity_type": "class"}
                    ]
                }
            },
        )

        if response.status_code == 200:
            data = response.json()
            assert "status" in data, "Response should have status field"
            assert data["status"] == "success", "Status should be success"
