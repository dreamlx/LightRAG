"""
测试 WorkspaceManager 动态 Workspace 路由 - TDD 先行

运行方式:
    pytest tests/test_workspace_manager.py -v
    pytest tests/test_workspace_manager.py -v -k "test_default"
"""

import asyncio

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
def base_config():
    """Base configuration for LightRAG instances."""
    return {
        "llm_model_func": mock_llm_func,
        "embedding_func": EmbeddingFunc(
            embedding_dim=384,
            max_token_size=8192,
            func=mock_embedding_func,
        ),
    }


@pytest.fixture
async def workspace_manager(tmp_path, base_config):
    """Create a WorkspaceManager for testing."""
    from lightrag.api.workspace_manager import WorkspaceManager

    manager = WorkspaceManager(
        base_config=base_config,
        working_dir=str(tmp_path / "rag_storage"),
    )
    yield manager
    await manager.close_all()


# =============================================================================
# Test: WorkspaceManager Core
# =============================================================================


class TestWorkspaceManagerCore:
    """测试 WorkspaceManager 核心功能."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_default_workspace(self, workspace_manager):
        """TC-01: 无指定时使用 default workspace."""
        rag = await workspace_manager.get_instance()
        assert rag is not None
        assert rag.workspace == "default"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_default_workspace_empty_string(self, workspace_manager):
        """空字符串时使用 default workspace."""
        rag = await workspace_manager.get_instance("")
        assert rag.workspace == "default"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_specified_workspace(self, workspace_manager):
        """TC-02: 指定 workspace 时正确创建."""
        rag = await workspace_manager.get_instance("erp")
        assert rag is not None
        assert rag.workspace == "erp"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_workspace_reuse(self, workspace_manager):
        """同一 workspace 返回相同实例."""
        rag1 = await workspace_manager.get_instance("crm")
        rag2 = await workspace_manager.get_instance("crm")
        assert rag1 is rag2

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_different_workspaces(self, workspace_manager):
        """不同 workspace 返回不同实例."""
        rag_erp = await workspace_manager.get_instance("erp")
        rag_crm = await workspace_manager.get_instance("crm")
        assert rag_erp is not rag_crm
        assert rag_erp.workspace == "erp"
        assert rag_crm.workspace == "crm"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_list_workspaces(self, workspace_manager):
        """列出已加载的 workspace."""
        await workspace_manager.get_instance("erp")
        await workspace_manager.get_instance("crm")

        workspaces = workspace_manager.list_workspaces()
        assert "erp" in workspaces
        assert "crm" in workspaces


class TestWorkspaceValidation:
    """测试 workspace 名称验证."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_valid_names(self, workspace_manager):
        """有效的 workspace 名称."""
        valid_names = ["erp", "crm_v2", "project-123", "MyProject"]
        for name in valid_names:
            rag = await workspace_manager.get_instance(name)
            assert rag.workspace == name

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_invalid_path_traversal(self, workspace_manager):
        """TC-04: 拒绝路径遍历攻击."""
        invalid_names = [
            "../../../etc/passwd",
            "..\\windows\\system32",
            "foo/../bar",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError):
                await workspace_manager.get_instance(name)

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_invalid_special_chars(self, workspace_manager):
        """拒绝特殊字符."""
        invalid_names = [
            "foo/bar",
            "foo\\bar",
            "foo bar",
            "foo@bar",
            "foo:bar",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError):
                await workspace_manager.get_instance(name)

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_too_long_name(self, workspace_manager):
        """拒绝过长名称."""
        long_name = "a" * 65  # 超过 64 字符
        with pytest.raises(ValueError):
            await workspace_manager.get_instance(long_name)

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_max_length_name(self, workspace_manager):
        """接受最大长度名称."""
        max_name = "a" * 64
        rag = await workspace_manager.get_instance(max_name)
        assert rag.workspace == max_name


class TestWorkspaceIsolation:
    """测试 workspace 数据隔离."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_data_isolation(self, workspace_manager):
        """TC-03: 不同 workspace 数据隔离."""
        # 获取两个 workspace
        rag_erp = await workspace_manager.get_instance("erp")
        rag_crm = await workspace_manager.get_instance("crm")

        # 在 erp 中插入数据
        await rag_erp.ainsert_custom_kg({
            "entities": [
                {"entity_name": "ERPEntity", "entity_type": "class"}
            ]
        })

        # 在 crm 中插入不同数据
        await rag_crm.ainsert_custom_kg({
            "entities": [
                {"entity_name": "CRMEntity", "entity_type": "class"}
            ]
        })

        # 验证 erp 有 ERPEntity，无 CRMEntity
        has_erp = await rag_erp.chunk_entity_relation_graph.has_node("ERPEntity")
        has_crm_in_erp = await rag_erp.chunk_entity_relation_graph.has_node("CRMEntity")
        assert has_erp, "ERPEntity should exist in erp workspace"
        assert not has_crm_in_erp, "CRMEntity should NOT exist in erp workspace"

        # 验证 crm 有 CRMEntity，无 ERPEntity
        has_crm = await rag_crm.chunk_entity_relation_graph.has_node("CRMEntity")
        has_erp_in_crm = await rag_crm.chunk_entity_relation_graph.has_node("ERPEntity")
        assert has_crm, "CRMEntity should exist in crm workspace"
        assert not has_erp_in_crm, "ERPEntity should NOT exist in crm workspace"


class TestConcurrency:
    """测试并发安全."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_concurrent_same_workspace(self, workspace_manager):
        """TC-05: 并发请求同一 workspace 只创建一次."""
        results = await asyncio.gather(*[
            workspace_manager.get_instance("concurrent_test")
            for _ in range(10)
        ])

        # 所有结果应该是同一个实例
        first = results[0]
        for rag in results[1:]:
            assert rag is first

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_concurrent_different_workspaces(self, workspace_manager):
        """并发创建不同 workspace."""
        workspace_names = [f"ws_{i}" for i in range(5)]

        results = await asyncio.gather(*[
            workspace_manager.get_instance(name)
            for name in workspace_names
        ])

        # 每个 workspace 应该是不同实例
        workspaces = [rag.workspace for rag in results]
        assert len(set(workspaces)) == len(workspace_names)
