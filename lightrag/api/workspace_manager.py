"""
WorkspaceManager - 动态 Workspace 路由管理器

支持单进程内多 workspace 的 LightRAG 实例管理，实现：
- 懒加载：按需创建 LightRAG 实例
- 数据隔离：不同 workspace 独立存储
- 向后兼容：无 Header 时使用 default workspace
- 并发安全：双重检查锁定

使用方式:
    manager = WorkspaceManager(base_config, working_dir)
    rag = await manager.get_instance("erp")
    await rag.ainsert_custom_kg(...)
"""

import asyncio
import logging
import re
from typing import Any, Optional

from lightrag import LightRAG

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """管理多个 workspace 的 LightRAG 实例（懒加载）"""

    # Workspace 名称验证：字母、数字、下划线、连字符，1-64 字符
    WORKSPACE_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
    DEFAULT_WORKSPACE = "default"

    def __init__(self, base_config: dict[str, Any], working_dir: str):
        """
        初始化 WorkspaceManager.

        Args:
            base_config: LightRAG 基础配置（LLM、Embedding 等）
            working_dir: 工作目录，各 workspace 在此下创建子目录
        """
        self._instances: dict[str, LightRAG] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._base_config = base_config
        self._working_dir = working_dir

    def validate_workspace(self, workspace: Optional[str]) -> str:
        """
        验证并规范化 workspace 名称.

        Args:
            workspace: 原始 workspace 名称

        Returns:
            规范化后的 workspace 名称

        Raises:
            ValueError: 如果名称无效
        """
        # 处理 None 和空字符串
        if workspace is None:
            return self.DEFAULT_WORKSPACE

        workspace = workspace.strip()
        if not workspace:
            return self.DEFAULT_WORKSPACE

        # 验证格式
        if not self.WORKSPACE_PATTERN.match(workspace):
            raise ValueError(
                f"Invalid workspace name: '{workspace}'. "
                f"Must match pattern: {self.WORKSPACE_PATTERN.pattern}"
            )

        return workspace

    async def get_instance(self, workspace: Optional[str] = None) -> LightRAG:
        """
        获取或创建 workspace 对应的 LightRAG 实例.

        使用双重检查锁定确保并发安全，同时最小化锁竞争。

        Args:
            workspace: workspace 名称，None 或空字符串使用 default

        Returns:
            对应 workspace 的 LightRAG 实例
        """
        workspace = self.validate_workspace(workspace)

        # 快速路径：已存在直接返回
        if workspace in self._instances:
            return self._instances[workspace]

        # 获取或创建 workspace 专用锁
        async with self._global_lock:
            if workspace not in self._locks:
                self._locks[workspace] = asyncio.Lock()
                logger.debug(f"Created lock for workspace: {workspace}")

        # 双重检查锁定
        async with self._locks[workspace]:
            if workspace not in self._instances:
                logger.info(f"Creating LightRAG instance for workspace: {workspace}")
                rag = LightRAG(
                    working_dir=self._working_dir,
                    workspace=workspace,
                    **self._base_config,
                )
                await rag.initialize_storages()
                self._instances[workspace] = rag
                logger.info(f"LightRAG instance created for workspace: {workspace}")

        return self._instances[workspace]

    async def close_instance(self, workspace: str) -> bool:
        """
        关闭指定 workspace 的实例.

        Args:
            workspace: workspace 名称

        Returns:
            是否成功关闭
        """
        workspace = self.validate_workspace(workspace)

        if workspace not in self._instances:
            return False

        try:
            rag = self._instances.pop(workspace)
            await rag.finalize_storages()
            logger.info(f"Closed LightRAG instance for workspace: {workspace}")
            return True
        except Exception as e:
            logger.error(f"Error closing workspace {workspace}: {e}")
            return False

    async def close_all(self):
        """关闭所有实例."""
        workspaces = list(self._instances.keys())
        for workspace in workspaces:
            try:
                rag = self._instances.pop(workspace, None)
                if rag:
                    await rag.finalize_storages()
                    logger.info(f"Closed workspace: {workspace}")
            except Exception as e:
                logger.error(f"Error closing workspace {workspace}: {e}")

        self._instances.clear()
        logger.info("All workspace instances closed")

    def list_workspaces(self) -> list[str]:
        """列出已加载的 workspace."""
        return list(self._instances.keys())

    def is_loaded(self, workspace: str) -> bool:
        """检查 workspace 是否已加载."""
        try:
            workspace = self.validate_workspace(workspace)
            return workspace in self._instances
        except ValueError:
            return False

    @property
    def instance_count(self) -> int:
        """返回已加载的实例数量."""
        return len(self._instances)
