"""
LoomGraph 集成示例 - 代码索引场景

演示如何使用 LightRAG API 存储和检索代码结构信息。

用法:
    # 设置环境变量 (如果使用真实 LLM/Embedding)
    export OPENAI_API_KEY="your-api-key"

    # 运行示例
    python examples/loomgraph_integration_demo.py

数据流:
    codeindex 解析结果 → LoomGraph 转换 → LightRAG API → 知识图谱存储

字段映射约定:
    - entity_type: 直接使用 (method, class, function, module)
    - signature, language, docstring: 拼接到 description
    - file_path: 直接使用
    - line_range: 存入 source_id (如 "src/auth.py:12-25")
    - relation_type: 存入 keywords (如 "CALLS", "INHERITS", "IMPORTS")
    - embedding: 不传，让 LightRAG 自动生成
"""

import asyncio
import os
import shutil
from pathlib import Path

# LightRAG imports
from lightrag import LightRAG, QueryParam


# =============================================================================
# Configuration
# =============================================================================

DEMO_WORKING_DIR = "./loomgraph_demo_storage"

# Use mock functions for demo (no API key required)
USE_MOCK = True


# =============================================================================
# Mock Functions (for offline demo)
# =============================================================================

if USE_MOCK:
    import numpy as np
    from lightrag.utils import EmbeddingFunc

    async def mock_llm_func(prompt, **kwargs):
        """Mock LLM for demo."""
        return "This is a mock LLM response for demonstration purposes."

    async def mock_embedding_func(texts: list[str]) -> np.ndarray:
        """Mock embedding for demo."""
        return np.random.rand(len(texts), 384).astype(np.float32)

    mock_embedding_func.embedding_dim = 384
    mock_embedding_func.max_token_size = 8192


# =============================================================================
# Demo Functions
# =============================================================================


async def create_rag_instance() -> LightRAG:
    """创建 LightRAG 实例."""
    if USE_MOCK:
        rag = LightRAG(
            working_dir=DEMO_WORKING_DIR,
            llm_model_func=mock_llm_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=384,
                max_token_size=8192,
                func=mock_embedding_func,
            ),
        )
    else:
        # 使用真实的 LLM/Embedding (需要设置环境变量)
        from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

        rag = LightRAG(
            working_dir=DEMO_WORKING_DIR,
            llm_model_func=gpt_4o_mini_complete,
            embedding_func=openai_embed,
        )

    await rag.initialize_storages()
    return rag


async def demo_create_entities(rag: LightRAG):
    """演示创建代码实体 (Entity)."""
    print("\n" + "=" * 60)
    print("Step 1: 创建代码实体 (Entities)")
    print("=" * 60)

    # 模拟 codeindex 解析结果
    entities = [
        {
            "name": "auth.AuthService",
            "data": {
                "entity_type": "class",
                "description": "class AuthService | Authentication service for user management | Python",
                "source_id": "src/auth.py:1-100",
                "file_path": "src/auth.py",
            },
        },
        {
            "name": "auth.AuthService.login",
            "data": {
                "entity_type": "method",
                "description": "def login(username: str, password: str) -> bool | Authenticate user credentials | Python",
                "source_id": "src/auth.py:10-30",
                "file_path": "src/auth.py",
            },
        },
        {
            "name": "auth.AuthService.logout",
            "data": {
                "entity_type": "method",
                "description": "def logout(session_id: str) -> None | End user session and cleanup | Python",
                "source_id": "src/auth.py:32-45",
                "file_path": "src/auth.py",
            },
        },
        {
            "name": "db.UserRepository",
            "data": {
                "entity_type": "class",
                "description": "class UserRepository | Database access layer for user data | Python",
                "source_id": "src/db.py:1-80",
                "file_path": "src/db.py",
            },
        },
        {
            "name": "db.UserRepository.find_by_username",
            "data": {
                "entity_type": "method",
                "description": "def find_by_username(username: str) -> User | Query user by username | Python",
                "source_id": "src/db.py:20-35",
                "file_path": "src/db.py",
            },
        },
        {
            "name": "models.User",
            "data": {
                "entity_type": "class",
                "description": "class User | User data model with authentication fields | Python",
                "source_id": "src/models.py:1-50",
                "file_path": "src/models.py",
            },
        },
    ]

    for entity in entities:
        result = await rag.acreate_entity(
            entity_name=entity["name"],
            entity_data=entity["data"],
        )
        print(f"  ✓ Created entity: {entity['name']}")

    print(f"\n  Total: {len(entities)} entities created")


async def demo_create_relations(rag: LightRAG):
    """演示创建代码关系 (Relations)."""
    print("\n" + "=" * 60)
    print("Step 2: 创建代码关系 (Relations)")
    print("=" * 60)

    # 模拟调用关系
    relations = [
        {
            "source": "auth.AuthService.login",
            "target": "db.UserRepository.find_by_username",
            "data": {
                "keywords": "CALLS",
                "description": "login method calls find_by_username to verify user credentials",
                "weight": 1.0,
                "source_id": "src/auth.py:15",
            },
        },
        {
            "source": "auth.AuthService",
            "target": "db.UserRepository",
            "data": {
                "keywords": "IMPORTS",
                "description": "AuthService imports UserRepository for database access",
                "weight": 1.0,
                "source_id": "src/auth.py:2",
            },
        },
        {
            "source": "db.UserRepository.find_by_username",
            "target": "models.User",
            "data": {
                "keywords": "RETURNS",
                "description": "find_by_username returns User model instance",
                "weight": 1.0,
                "source_id": "src/db.py:34",
            },
        },
    ]

    for rel in relations:
        result = await rag.acreate_relation(
            source_entity=rel["source"],
            target_entity=rel["target"],
            relation_data=rel["data"],
        )
        rel_type = rel["data"]["keywords"]
        print(f"  ✓ Created relation: {rel['source']} --[{rel_type}]--> {rel['target']}")

    print(f"\n  Total: {len(relations)} relations created")


async def demo_graph_traversal(rag: LightRAG):
    """演示图遍历查询."""
    print("\n" + "=" * 60)
    print("Step 3: 图遍历查询")
    print("=" * 60)

    # 查询某个节点的所有边
    entity_name = "auth.AuthService.login"
    edges = await rag.chunk_entity_relation_graph.get_node_edges(entity_name)

    print(f"\n  查询 '{entity_name}' 的所有关系:")
    if edges:
        for src, tgt in edges:
            print(f"    - {src} --> {tgt}")
    else:
        print("    (无关系)")

    # 检查节点是否存在
    print("\n  检查节点存在性:")
    test_nodes = ["auth.AuthService", "nonexistent.Module"]
    for node in test_nodes:
        exists = await rag.chunk_entity_relation_graph.has_node(node)
        status = "✓ 存在" if exists else "✗ 不存在"
        print(f"    - {node}: {status}")


async def demo_semantic_search(rag: LightRAG):
    """演示语义搜索 (需要真实 LLM)."""
    print("\n" + "=" * 60)
    print("Step 4: 语义搜索 (Mock 模式下结果为模拟)")
    print("=" * 60)

    queries = [
        "用户认证相关的方法有哪些？",
        "如何从数据库查询用户？",
    ]

    for query in queries:
        print(f"\n  Query: {query}")
        try:
            result = await rag.aquery(query, param=QueryParam(mode="local"))
            # Truncate long results
            display_result = result[:200] + "..." if len(result) > 200 else result
            print(f"  Result: {display_result}")
        except Exception as e:
            print(f"  Error: {e}")


async def demo_deletion(rag: LightRAG):
    """演示删除操作."""
    print("\n" + "=" * 60)
    print("Step 5: 删除操作 (级联删除)")
    print("=" * 60)

    entity_to_delete = "auth.AuthService.logout"

    # 删除前检查
    exists_before = await rag.chunk_entity_relation_graph.has_node(entity_to_delete)
    print(f"\n  删除前: '{entity_to_delete}' 存在 = {exists_before}")

    # 执行删除
    result = await rag.adelete_by_entity(entity_to_delete)
    print(f"  执行删除...")

    # 删除后检查
    exists_after = await rag.chunk_entity_relation_graph.has_node(entity_to_delete)
    print(f"  删除后: '{entity_to_delete}' 存在 = {exists_after}")


async def demo_full_rebuild(rag: LightRAG):
    """演示全量重建."""
    print("\n" + "=" * 60)
    print("Step 6: 全量重建 (MVP 核心功能)")
    print("=" * 60)

    print("\n  模拟全量重建流程:")
    print("  1. finalize_storages() - 关闭存储")
    print("  2. shutil.rmtree(working_dir) - 清空目录")
    print("  3. initialize_storages() - 重新初始化")
    print("  4. 重新注入数据")

    print("\n  [跳过实际执行以保留 demo 数据]")


async def main():
    """主函数."""
    print("=" * 60)
    print("LoomGraph + LightRAG 集成示例")
    print("=" * 60)

    # 清理旧数据
    if Path(DEMO_WORKING_DIR).exists():
        shutil.rmtree(DEMO_WORKING_DIR)
        print(f"\n清理旧数据: {DEMO_WORKING_DIR}")

    # 创建 RAG 实例
    rag = await create_rag_instance()
    print(f"创建 LightRAG 实例: {DEMO_WORKING_DIR}")

    try:
        # 运行演示
        await demo_create_entities(rag)
        await demo_create_relations(rag)
        await demo_graph_traversal(rag)
        await demo_semantic_search(rag)
        await demo_deletion(rag)
        await demo_full_rebuild(rag)

        print("\n" + "=" * 60)
        print("演示完成！")
        print("=" * 60)

    finally:
        await rag.finalize_storages()
        print(f"\n存储已关闭。数据保存在: {DEMO_WORKING_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
