"""
Test GET /api/workspaces endpoint and WorkspaceManager.discover_workspaces()

Run:
    pytest tests/test_workspace_list_api.py -v
"""

import os

import numpy as np
import pytest

from lightrag.utils import EmbeddingFunc


# =============================================================================
# Mock Functions
# =============================================================================


async def mock_llm_func(prompt, **kwargs):
    return "Mock LLM response"


async def mock_embedding_func(texts: list[str]) -> np.ndarray:
    return np.random.rand(len(texts), 384).astype(np.float32)


mock_embedding_func.embedding_dim = 384
mock_embedding_func.max_token_size = 8192


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def base_config():
    return {
        "llm_model_func": mock_llm_func,
        "embedding_func": EmbeddingFunc(
            embedding_dim=384,
            max_token_size=8192,
            func=mock_embedding_func,
        ),
    }


@pytest.fixture
def workspace_manager(tmp_path, base_config):
    from lightrag.api.workspace_manager import WorkspaceManager

    manager = WorkspaceManager(
        base_config=base_config,
        working_dir=str(tmp_path / "rag_storage"),
    )
    return manager


# =============================================================================
# Test: discover_workspaces
# =============================================================================


class TestDiscoverWorkspaces:
    """Test WorkspaceManager.discover_workspaces() method."""

    @pytest.mark.offline
    def test_empty_working_dir(self, workspace_manager, tmp_path):
        """TC-01: Empty working_dir returns empty list."""
        # working_dir doesn't exist yet
        result = workspace_manager.discover_workspaces()
        assert result == []

    @pytest.mark.offline
    def test_with_workspace_dirs(self, workspace_manager, tmp_path):
        """TC-02: Returns workspace directory names."""
        rag_dir = tmp_path / "rag_storage"
        rag_dir.mkdir()
        (rag_dir / "default").mkdir()
        (rag_dir / "erp").mkdir()
        (rag_dir / "crm").mkdir()

        result = workspace_manager.discover_workspaces()
        assert sorted(result) == ["crm", "default", "erp"]

    @pytest.mark.offline
    def test_ignores_hidden_dirs(self, workspace_manager, tmp_path):
        """TC-03: Hidden directories are ignored."""
        rag_dir = tmp_path / "rag_storage"
        rag_dir.mkdir()
        (rag_dir / "erp").mkdir()
        (rag_dir / ".hidden").mkdir()
        (rag_dir / ".git").mkdir()

        result = workspace_manager.discover_workspaces()
        assert result == ["erp"]

    @pytest.mark.offline
    def test_ignores_files(self, workspace_manager, tmp_path):
        """TC-04: Files (not dirs) are ignored."""
        rag_dir = tmp_path / "rag_storage"
        rag_dir.mkdir()
        (rag_dir / "erp").mkdir()
        (rag_dir / "some_file.json").write_text("{}")
        (rag_dir / "README.md").write_text("hello")

        result = workspace_manager.discover_workspaces()
        assert result == ["erp"]

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_includes_loaded_and_unloaded(self, workspace_manager, tmp_path):
        """TC-05: Returns both loaded and unloaded workspaces."""
        rag_dir = tmp_path / "rag_storage"
        rag_dir.mkdir()
        (rag_dir / "erp").mkdir()
        (rag_dir / "crm").mkdir()

        # Load only erp
        await workspace_manager.get_instance("erp")

        # discover should return both
        result = workspace_manager.discover_workspaces()
        assert "erp" in result
        assert "crm" in result

        await workspace_manager.close_all()

    @pytest.mark.offline
    def test_sorted_output(self, workspace_manager, tmp_path):
        """Workspaces should be returned in sorted order."""
        rag_dir = tmp_path / "rag_storage"
        rag_dir.mkdir()
        (rag_dir / "zebra").mkdir()
        (rag_dir / "alpha").mkdir()
        (rag_dir / "mid").mkdir()

        result = workspace_manager.discover_workspaces()
        assert result == ["alpha", "mid", "zebra"]
