"""
Test GET /graph/entities/all and GET /graph/relations/all endpoints

SDK layer tests (offline, no external services required).

Run:
    pytest tests/test_graph_all_endpoints.py -v
    pytest tests/test_graph_all_endpoints.py -v -k "test_get_all_nodes"
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
# Test: get_all_graph_nodes / get_all_graph_edges SDK methods
# =============================================================================


class TestGetAllGraphNodesSDK:
    """Test LightRAG.get_all_graph_nodes() SDK method."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_empty_graph_returns_empty_list(self, rag_instance):
        """Empty graph should return empty list."""
        nodes = await rag_instance.get_all_graph_nodes()
        assert isinstance(nodes, list)
        assert len(nodes) == 0

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_returns_inserted_entities(self, rag_instance):
        """Should return entities after insertion."""
        await rag_instance.ainsert_custom_kg({
            "entities": [
                {"entity_name": "AuthService", "entity_type": "class", "description": "Auth service"},
                {"entity_name": "UserModel", "entity_type": "class", "description": "User model"},
            ]
        })

        nodes = await rag_instance.get_all_graph_nodes()
        assert isinstance(nodes, list)
        assert len(nodes) >= 2

        node_ids = [n.get("id") or n.get("entity_id") for n in nodes]
        assert "AuthService" in node_ids
        assert "UserModel" in node_ids

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_node_contains_properties(self, rag_instance):
        """Each node should contain its properties."""
        await rag_instance.ainsert_custom_kg({
            "entities": [
                {"entity_name": "Config", "entity_type": "class", "description": "Config class"},
            ]
        })

        nodes = await rag_instance.get_all_graph_nodes()
        config_node = next((n for n in nodes if n.get("id") == "Config"), None)
        assert config_node is not None
        assert "entity_type" in config_node


class TestGetAllGraphEdgesSDK:
    """Test LightRAG.get_all_graph_edges() SDK method."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_empty_graph_returns_empty_list(self, rag_instance):
        """Empty graph should return empty list."""
        edges = await rag_instance.get_all_graph_edges()
        assert isinstance(edges, list)
        assert len(edges) == 0

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_returns_inserted_relations(self, rag_instance):
        """Should return relations after insertion."""
        await rag_instance.ainsert_custom_kg({
            "entities": [
                {"entity_name": "ClassA", "entity_type": "class"},
                {"entity_name": "ClassB", "entity_type": "class"},
            ],
            "relationships": [
                {
                    "src_id": "ClassA",
                    "tgt_id": "ClassB",
                    "description": "inherits from",
                    "keywords": "inheritance",
                    "weight": 1.0,
                },
            ],
        })

        edges = await rag_instance.get_all_graph_edges()
        assert isinstance(edges, list)
        assert len(edges) >= 1

        # Check edge has source/target
        edge = edges[0]
        assert "source" in edge or "src_id" in edge
        assert "target" in edge or "tgt_id" in edge

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_edge_contains_properties(self, rag_instance):
        """Each edge should contain its properties."""
        await rag_instance.ainsert_custom_kg({
            "relationships": [
                {
                    "src_id": "ServiceA",
                    "tgt_id": "ServiceB",
                    "description": "calls",
                    "keywords": "dependency,calls",
                    "weight": 2.0,
                },
            ],
        })

        edges = await rag_instance.get_all_graph_edges()
        assert len(edges) >= 1
        edge = edges[0]
        assert "description" in edge or "keywords" in edge
