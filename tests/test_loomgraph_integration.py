"""
LoomGraph 集成测试 - TDD 先行

测试 LightRAG API 是否满足代码索引场景需求。

运行方式:
    pytest tests/test_loomgraph_integration.py -v
    pytest tests/test_loomgraph_integration.py -v -k "test_create_method"
"""

import shutil
from unittest.mock import AsyncMock

import numpy as np
import pytest

from lightrag import LightRAG, QueryParam
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


# Add required attributes to mock embedding function
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
# Test: Entity Creation
# =============================================================================


class TestEntityCreation:
    """测试 Entity 创建功能 - 代码索引场景."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_create_method_entity(self, rag_instance):
        """测试创建 method 类型的 entity."""
        result = await rag_instance.acreate_entity(
            entity_name="auth.login",
            entity_data={
                "entity_type": "method",
                "description": "def login(username: str, password: str) -> bool | Authenticate user | Python",
                "source_id": "src/auth.py:12-25",
                "file_path": "src/auth.py",
            },
        )

        assert result is not None
        assert result.get("entity_name") == "auth.login"
        # entity_type is nested in graph_data
        assert result.get("graph_data", {}).get("entity_type") == "method"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_create_class_entity(self, rag_instance):
        """测试创建 class 类型的 entity."""
        result = await rag_instance.acreate_entity(
            entity_name="models.User",
            entity_data={
                "entity_type": "class",
                "description": "class User | User model with authentication | Python",
                "source_id": "src/models.py:1-50",
                "file_path": "src/models.py",
            },
        )

        assert result is not None
        assert result.get("graph_data", {}).get("entity_type") == "class"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_create_function_entity(self, rag_instance):
        """测试创建 function 类型的 entity."""
        result = await rag_instance.acreate_entity(
            entity_name="utils.hash_password",
            entity_data={
                "entity_type": "function",
                "description": "def hash_password(password: str) -> str | Hash password using bcrypt | Python",
                "source_id": "src/utils.py:10-20",
                "file_path": "src/utils.py",
            },
        )

        assert result is not None
        assert result.get("graph_data", {}).get("entity_type") == "function"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_create_duplicate_entity_raises_error(self, rag_instance):
        """测试创建重复 entity 应该抛错."""
        await rag_instance.acreate_entity(
            entity_name="auth.login",
            entity_data={"entity_type": "method", "description": "first"},
        )

        with pytest.raises(ValueError, match="already exists"):
            await rag_instance.acreate_entity(
                entity_name="auth.login",
                entity_data={"entity_type": "method", "description": "duplicate"},
            )

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_entity_with_signature_in_description(self, rag_instance):
        """测试将 signature 信息拼接到 description 中."""
        # LoomGraph 约定: signature, language 等拼接到 description
        description = "def login(username: str, password: str) -> bool | Authenticate user credentials | Python | src/auth.py:12-25"

        result = await rag_instance.acreate_entity(
            entity_name="auth.login",
            entity_data={
                "entity_type": "method",
                "description": description,
                "source_id": "src/auth.py:12-25",
                "file_path": "src/auth.py",
            },
        )

        assert result is not None
        # Verify description is stored in graph_data
        assert "description" in result.get("graph_data", {})
        assert description in result["graph_data"]["description"]


# =============================================================================
# Test: Relation Creation
# =============================================================================


class TestRelationCreation:
    """测试 Relation 创建功能 - 代码调用关系."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_create_calls_relation(self, rag_instance):
        """测试创建 CALLS 类型的 relation."""
        # Setup: 创建两个 entities
        await rag_instance.acreate_entity(
            entity_name="auth.login",
            entity_data={"entity_type": "method", "description": "login method"},
        )
        await rag_instance.acreate_entity(
            entity_name="db.query_user",
            entity_data={"entity_type": "method", "description": "query user from db"},
        )

        # Create CALLS relation
        result = await rag_instance.acreate_relation(
            source_entity="auth.login",
            target_entity="db.query_user",
            relation_data={
                "keywords": "CALLS",
                "description": "auth.login calls db.query_user to verify credentials",
                "weight": 1.0,
                "source_id": "src/auth.py:15",
            },
        )

        assert result is not None

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_create_inherits_relation(self, rag_instance):
        """测试创建 INHERITS 类型的 relation."""
        await rag_instance.acreate_entity(
            entity_name="models.Admin",
            entity_data={"entity_type": "class", "description": "Admin class"},
        )
        await rag_instance.acreate_entity(
            entity_name="models.User",
            entity_data={"entity_type": "class", "description": "User class"},
        )

        result = await rag_instance.acreate_relation(
            source_entity="models.Admin",
            target_entity="models.User",
            relation_data={
                "keywords": "INHERITS",
                "description": "Admin inherits from User",
                "weight": 1.0,
            },
        )

        assert result is not None

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_create_imports_relation(self, rag_instance):
        """测试创建 IMPORTS 类型的 relation."""
        await rag_instance.acreate_entity(
            entity_name="auth",
            entity_data={"entity_type": "module", "description": "auth module"},
        )
        await rag_instance.acreate_entity(
            entity_name="db",
            entity_data={"entity_type": "module", "description": "db module"},
        )

        result = await rag_instance.acreate_relation(
            source_entity="auth",
            target_entity="db",
            relation_data={
                "keywords": "IMPORTS",
                "description": "auth imports db module",
                "weight": 1.0,
            },
        )

        assert result is not None

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_relation_with_nonexistent_source_raises_error(self, rag_instance):
        """测试创建关系时源 entity 不存在应该抛错."""
        await rag_instance.acreate_entity(
            entity_name="existing",
            entity_data={"entity_type": "method", "description": "exists"},
        )

        with pytest.raises(ValueError, match="does not exist"):
            await rag_instance.acreate_relation(
                source_entity="nonexistent",
                target_entity="existing",
                relation_data={"keywords": "CALLS", "description": "test"},
            )

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_relation_with_nonexistent_target_raises_error(self, rag_instance):
        """测试创建关系时目标 entity 不存在应该抛错."""
        await rag_instance.acreate_entity(
            entity_name="existing",
            entity_data={"entity_type": "method", "description": "exists"},
        )

        with pytest.raises(ValueError, match="does not exist"):
            await rag_instance.acreate_relation(
                source_entity="existing",
                target_entity="nonexistent",
                relation_data={"keywords": "CALLS", "description": "test"},
            )

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_duplicate_relation_raises_error(self, rag_instance):
        """测试创建重复 relation 应该抛错."""
        await rag_instance.acreate_entity(
            entity_name="a",
            entity_data={"entity_type": "method", "description": "a"},
        )
        await rag_instance.acreate_entity(
            entity_name="b",
            entity_data={"entity_type": "method", "description": "b"},
        )

        await rag_instance.acreate_relation(
            source_entity="a",
            target_entity="b",
            relation_data={"keywords": "CALLS", "description": "first"},
        )

        with pytest.raises(ValueError, match="already exists"):
            await rag_instance.acreate_relation(
                source_entity="a",
                target_entity="b",
                relation_data={"keywords": "CALLS", "description": "duplicate"},
            )


# =============================================================================
# Test: Graph Traversal
# =============================================================================


class TestGraphTraversal:
    """测试图遍历功能 - 代码依赖分析."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_get_node_edges(self, rag_instance):
        """测试获取节点的所有边."""
        # Setup: 创建一个中心节点和多个关联节点
        await rag_instance.acreate_entity(
            entity_name="auth.AuthService",
            entity_data={"entity_type": "class", "description": "Auth service"},
        )
        await rag_instance.acreate_entity(
            entity_name="auth.login",
            entity_data={"entity_type": "method", "description": "login method"},
        )
        await rag_instance.acreate_entity(
            entity_name="auth.logout",
            entity_data={"entity_type": "method", "description": "logout method"},
        )

        await rag_instance.acreate_relation(
            source_entity="auth.AuthService",
            target_entity="auth.login",
            relation_data={"keywords": "CONTAINS", "description": "contains login"},
        )
        await rag_instance.acreate_relation(
            source_entity="auth.AuthService",
            target_entity="auth.logout",
            relation_data={"keywords": "CONTAINS", "description": "contains logout"},
        )

        # Test: 获取 AuthService 的所有边
        edges = await rag_instance.chunk_entity_relation_graph.get_node_edges(
            "auth.AuthService"
        )

        assert edges is not None
        assert len(edges) == 2

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_get_node_edges_no_edges(self, rag_instance):
        """测试获取没有边的节点."""
        await rag_instance.acreate_entity(
            entity_name="isolated",
            entity_data={"entity_type": "class", "description": "isolated node"},
        )

        edges = await rag_instance.chunk_entity_relation_graph.get_node_edges("isolated")

        # Should return None or empty list
        assert edges is None or len(edges) == 0

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_has_node(self, rag_instance):
        """测试检查节点是否存在."""
        await rag_instance.acreate_entity(
            entity_name="exists",
            entity_data={"entity_type": "class", "description": "exists"},
        )

        has_exists = await rag_instance.chunk_entity_relation_graph.has_node("exists")
        has_not_exists = await rag_instance.chunk_entity_relation_graph.has_node(
            "not_exists"
        )

        assert has_exists is True
        assert has_not_exists is False


# =============================================================================
# Test: Deletion
# =============================================================================


class TestDeletion:
    """测试删除功能 - 代码重构场景."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_delete_entity_removes_node(self, rag_instance):
        """测试删除 entity 移除节点."""
        await rag_instance.acreate_entity(
            entity_name="to_delete",
            entity_data={"entity_type": "class", "description": "will be deleted"},
        )

        # Delete
        await rag_instance.adelete_by_entity("to_delete")

        # Verify node is gone
        has_node = await rag_instance.chunk_entity_relation_graph.has_node("to_delete")
        assert has_node is False

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_delete_entity_cascades_relations(self, rag_instance):
        """测试删除 entity 时自动删除关联的 relations."""
        # Setup
        await rag_instance.acreate_entity(
            entity_name="to_delete",
            entity_data={"entity_type": "class", "description": "del"},
        )
        await rag_instance.acreate_entity(
            entity_name="related",
            entity_data={"entity_type": "method", "description": "rel"},
        )
        await rag_instance.acreate_relation(
            source_entity="to_delete",
            target_entity="related",
            relation_data={"keywords": "CALLS", "description": "r"},
        )

        # Verify relation exists before deletion
        edges_before = await rag_instance.chunk_entity_relation_graph.get_node_edges(
            "related"
        )
        assert edges_before is not None and len(edges_before) > 0

        # Delete entity
        await rag_instance.adelete_by_entity("to_delete")

        # Verify relation is also gone
        edges_after = await rag_instance.chunk_entity_relation_graph.get_node_edges(
            "related"
        )
        assert edges_after is None or len(edges_after) == 0

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_delete_nonexistent_entity(self, rag_instance):
        """测试删除不存在的 entity 应该返回错误或空结果."""
        result = await rag_instance.adelete_by_entity("nonexistent")

        # Should indicate not found (either via return value or not raising)
        assert result is not None
        assert result.status_code == 404 or "not found" in str(result).lower()


# =============================================================================
# Test: Full Rebuild
# =============================================================================


class TestFullRebuild:
    """测试全量重建场景 - MVP 核心功能."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_clear_working_dir_and_rebuild(self, tmp_path):
        """测试清空 working_dir 后重建.

        注意: 需要创建新的 LightRAG 实例，因为内存中的图存储会保留数据。
        """
        working_dir = str(tmp_path / "rag_rebuild_test")

        # Phase 1: 创建并填充数据
        rag1 = LightRAG(
            working_dir=working_dir,
            llm_model_func=mock_llm_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=384,
                max_token_size=8192,
                func=mock_embedding_func,
            ),
        )
        await rag1.initialize_storages()

        await rag1.acreate_entity(
            entity_name="old_entity",
            entity_data={"entity_type": "class", "description": "old data"},
        )

        has_old = await rag1.chunk_entity_relation_graph.has_node("old_entity")
        assert has_old is True

        await rag1.finalize_storages()

        # Phase 2: 清空目录
        shutil.rmtree(working_dir, ignore_errors=True)

        # Phase 3: 创建新实例验证数据已清空
        rag2 = LightRAG(
            working_dir=working_dir,
            llm_model_func=mock_llm_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=384,
                max_token_size=8192,
                func=mock_embedding_func,
            ),
        )
        await rag2.initialize_storages()

        # Verify old data is gone
        has_old_after = await rag2.chunk_entity_relation_graph.has_node("old_entity")
        assert has_old_after is False

        # Rebuild with new data
        await rag2.acreate_entity(
            entity_name="new_entity",
            entity_data={"entity_type": "class", "description": "new data"},
        )

        has_new = await rag2.chunk_entity_relation_graph.has_node("new_entity")
        assert has_new is True

        await rag2.finalize_storages()

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_rebuild_preserves_api_functionality(self, rag_instance, tmp_path):
        """测试重建后 API 功能正常."""
        # Clear and rebuild
        await rag_instance.finalize_storages()
        shutil.rmtree(rag_instance.working_dir, ignore_errors=True)
        await rag_instance.initialize_storages()

        # Create entities
        await rag_instance.acreate_entity(
            entity_name="auth.login",
            entity_data={"entity_type": "method", "description": "login"},
        )
        await rag_instance.acreate_entity(
            entity_name="db.query",
            entity_data={"entity_type": "method", "description": "query"},
        )

        # Create relation
        await rag_instance.acreate_relation(
            source_entity="auth.login",
            target_entity="db.query",
            relation_data={"keywords": "CALLS", "description": "calls"},
        )

        # Verify all operations work
        has_login = await rag_instance.chunk_entity_relation_graph.has_node("auth.login")
        edges = await rag_instance.chunk_entity_relation_graph.get_node_edges(
            "auth.login"
        )

        assert has_login is True
        assert edges is not None and len(edges) == 1


# =============================================================================
# Test: Code Index Workflow (Integration)
# =============================================================================


class TestCodeIndexWorkflow:
    """测试完整的代码索引工作流."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_complete_code_index_workflow(self, rag_instance):
        """测试完整的代码索引工作流: 解析 -> 注入 -> 查询."""
        # Step 1: 模拟 codeindex 输出并注入
        # 创建 entities (模拟代码解析结果)
        entities = [
            {
                "name": "auth.AuthService",
                "data": {
                    "entity_type": "class",
                    "description": "class AuthService | Authentication service | Python",
                    "source_id": "src/auth.py:1-100",
                    "file_path": "src/auth.py",
                },
            },
            {
                "name": "auth.AuthService.login",
                "data": {
                    "entity_type": "method",
                    "description": "def login(username, password) -> bool | Authenticate user | Python",
                    "source_id": "src/auth.py:10-30",
                    "file_path": "src/auth.py",
                },
            },
            {
                "name": "auth.AuthService.logout",
                "data": {
                    "entity_type": "method",
                    "description": "def logout(session_id) -> None | End user session | Python",
                    "source_id": "src/auth.py:32-45",
                    "file_path": "src/auth.py",
                },
            },
            {
                "name": "db.UserRepository",
                "data": {
                    "entity_type": "class",
                    "description": "class UserRepository | Database access for users | Python",
                    "source_id": "src/db.py:1-80",
                    "file_path": "src/db.py",
                },
            },
            {
                "name": "db.UserRepository.find_by_username",
                "data": {
                    "entity_type": "method",
                    "description": "def find_by_username(username) -> User | Find user by username | Python",
                    "source_id": "src/db.py:20-35",
                    "file_path": "src/db.py",
                },
            },
        ]

        for entity in entities:
            await rag_instance.acreate_entity(
                entity_name=entity["name"], entity_data=entity["data"]
            )

        # Step 2: 创建 relations (模拟调用关系)
        relations = [
            {
                "source": "auth.AuthService.login",
                "target": "db.UserRepository.find_by_username",
                "data": {
                    "keywords": "CALLS",
                    "description": "login calls find_by_username to verify user",
                    "weight": 1.0,
                    "source_id": "src/auth.py:15",
                },
            },
            {
                "source": "auth.AuthService",
                "target": "db.UserRepository",
                "data": {
                    "keywords": "IMPORTS",
                    "description": "AuthService imports UserRepository",
                    "weight": 1.0,
                },
            },
        ]

        for rel in relations:
            await rag_instance.acreate_relation(
                source_entity=rel["source"],
                target_entity=rel["target"],
                relation_data=rel["data"],
            )

        # Step 3: 验证图结构
        # Check all entities exist
        for entity in entities:
            has_node = await rag_instance.chunk_entity_relation_graph.has_node(
                entity["name"]
            )
            assert has_node is True, f"Entity {entity['name']} should exist"

        # Check relations
        edges = await rag_instance.chunk_entity_relation_graph.get_node_edges(
            "auth.AuthService.login"
        )
        assert edges is not None and len(edges) >= 1

        # Step 4: 验证可以删除并重建
        await rag_instance.adelete_by_entity("auth.AuthService.login")

        has_deleted = await rag_instance.chunk_entity_relation_graph.has_node(
            "auth.AuthService.login"
        )
        assert has_deleted is False
