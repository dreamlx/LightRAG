# Feature: 动态 Workspace 路由

## 概述

为 LightRAG API 添加 WorkspaceManager，支持单进程内多 workspace 动态路由，实现一个客户多项目的数据隔离。

## 背景

### 当前架构
- 每个客户 = 1 个 LightRAG 进程 (独立端口)
- 每个进程 = 固定 1 个 workspace
- 多项目需要启动多个进程

### 目标架构
- 每个客户 = 1 个 LightRAG 进程
- 每个进程 = 动态多 workspace (按需加载)
- 通过 HTTP Header 指定 workspace

## 设计

### 架构图

```
拼便宜客户机器:                        H200 服务器:
┌─────────────────────┐               ┌─────────────────────────────┐
│ LoomGraph           │               │ LightRAG :3010              │
│                     │               │ ┌─────────────────────────┐ │
│ POST /insert...     │               │ │ WorkspaceManager        │ │
│ Header:             │ ────────────> │ │  ├─ "default" → rag_0   │ │
│   LIGHTRAG-WORKSPACE│               │ │  ├─ "erp"     → rag_1   │ │
│   : erp             │               │ │  └─ "crm"     → rag_2   │ │
│                     │               │ └─────────────────────────┘ │
└─────────────────────┘               │           ↓                 │
                                      │    共享 LLM/Embedding       │
                                      │    独立 Storage 目录        │
                                      └─────────────────────────────┘
```

### 向后兼容

| 场景 | Header | 行为 |
|------|--------|------|
| 现有 MVP | 无 | 使用 "default" workspace |
| 多项目 | `LIGHTRAG-WORKSPACE: erp` | 使用 "erp" workspace |

### 存储隔离

```
~/lightrag-projects/pinpianyi_default/
├── rag_storage/
│   ├── default/          ← workspace "default"
│   │   ├── graph_chunk_entity_relation.graphml
│   │   ├── kv_store_*.json
│   │   └── vdb_*.json
│   ├── erp/              ← workspace "erp"
│   │   └── ...
│   └── crm/              ← workspace "crm"
│       └── ...
└── .env
```

## API 规格

### Header

```
LIGHTRAG-WORKSPACE: <workspace_name>
```

- 可选，默认 "default"
- 仅支持字母、数字、下划线、连字符
- 最大长度 64 字符

### 受影响的端点

| 端点 | 支持 Workspace |
|------|----------------|
| `POST /documents/insert_custom_kg` | ✅ |
| `POST /query` | ✅ |
| `DELETE /documents` | ✅ |
| `GET /health` | ✅ (显示当前 workspace) |

## 实现

### 1. WorkspaceManager 类

```python
# lightrag/api/workspace_manager.py

import asyncio
import re
from typing import Optional
from lightrag import LightRAG

class WorkspaceManager:
    """管理多个 workspace 的 LightRAG 实例（懒加载）"""

    WORKSPACE_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
    DEFAULT_WORKSPACE = "default"

    def __init__(self, base_config: dict, working_dir: str):
        self._instances: dict[str, LightRAG] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._base_config = base_config
        self._working_dir = working_dir

    def validate_workspace(self, workspace: str) -> str:
        """验证并规范化 workspace 名称"""
        workspace = workspace.strip() if workspace else self.DEFAULT_WORKSPACE
        if not workspace:
            return self.DEFAULT_WORKSPACE
        if not self.WORKSPACE_PATTERN.match(workspace):
            raise ValueError(f"Invalid workspace name: {workspace}")
        return workspace

    async def get_instance(self, workspace: str = None) -> LightRAG:
        """获取或创建 workspace 对应的 LightRAG 实例"""
        workspace = self.validate_workspace(workspace)

        if workspace in self._instances:
            return self._instances[workspace]

        # Double-checked locking
        async with self._global_lock:
            if workspace not in self._locks:
                self._locks[workspace] = asyncio.Lock()

        async with self._locks[workspace]:
            if workspace not in self._instances:
                rag = LightRAG(
                    working_dir=self._working_dir,
                    workspace=workspace,
                    **self._base_config
                )
                await rag.initialize_storages()
                self._instances[workspace] = rag

        return self._instances[workspace]

    async def close_all(self):
        """关闭所有实例"""
        for workspace, rag in self._instances.items():
            try:
                await rag.finalize_storages()
            except Exception as e:
                logger.error(f"Error closing workspace {workspace}: {e}")
        self._instances.clear()

    def list_workspaces(self) -> list[str]:
        """列出已加载的 workspace"""
        return list(self._instances.keys())
```

### 2. 路由集成

```python
# 修改 lightrag_server.py

from fastapi import Request, Depends

def get_workspace_manager() -> WorkspaceManager:
    return app.state.workspace_manager

async def get_rag_for_request(
    request: Request,
    manager: WorkspaceManager = Depends(get_workspace_manager)
) -> LightRAG:
    """从请求 Header 获取对应的 LightRAG 实例"""
    workspace = request.headers.get("LIGHTRAG-WORKSPACE", "")
    return await manager.get_instance(workspace)
```

### 3. 端点修改示例

```python
@router.post("/documents/insert_custom_kg")
async def insert_custom_kg(
    request: InsertCustomKGRequest,
    rag: LightRAG = Depends(get_rag_for_request)
):
    await rag.ainsert_custom_kg(request.custom_kg.model_dump())
    return {"status": "success", ...}
```

## 测试用例

### TC-01: 默认 workspace

```python
async def test_default_workspace():
    """无 Header 时使用 default workspace"""
    response = client.post("/documents/insert_custom_kg", json={...})
    # 数据应存入 default workspace
```

### TC-02: 指定 workspace

```python
async def test_specified_workspace():
    """Header 指定 workspace"""
    response = client.post(
        "/documents/insert_custom_kg",
        headers={"LIGHTRAG-WORKSPACE": "erp"},
        json={...}
    )
    # 数据应存入 erp workspace
```

### TC-03: workspace 隔离

```python
async def test_workspace_isolation():
    """不同 workspace 数据隔离"""
    # 插入到 erp
    client.post(..., headers={"LIGHTRAG-WORKSPACE": "erp"})

    # 从 crm 查询，不应找到
    response = client.post(
        "/query",
        headers={"LIGHTRAG-WORKSPACE": "crm"},
        json={"query": "..."}
    )
    # 应返回空或不相关结果
```

### TC-04: 无效 workspace 名称

```python
async def test_invalid_workspace():
    """拒绝无效 workspace 名称"""
    response = client.post(
        ...,
        headers={"LIGHTRAG-WORKSPACE": "../../../etc/passwd"}
    )
    assert response.status_code == 400
```

### TC-05: 并发创建

```python
async def test_concurrent_creation():
    """并发请求同一 workspace 只创建一次"""
    tasks = [
        client.post(..., headers={"LIGHTRAG-WORKSPACE": "new_ws"})
        for _ in range(10)
    ]
    await asyncio.gather(*tasks)
    # 应只有一个 new_ws 实例
```

## 验收标准

- [ ] 无 Header 时使用 default workspace (向后兼容)
- [ ] Header 指定 workspace 时正确路由
- [ ] 不同 workspace 数据完全隔离
- [ ] 无效 workspace 名称返回 400
- [ ] 并发安全
- [ ] 现有测试不受影响

## LoomGraph 配置示例

```yaml
# ~/.loomgraph/config.yaml

lightrag:
  endpoint: http://117.131.45.179:3010
  timeout: 300

projects:
  - name: erp
    path: /home/dev/projects/erp-system
    workspace: erp  # 对应 LIGHTRAG-WORKSPACE header

  - name: crm
    path: /home/dev/projects/crm-app
    workspace: crm

  - name: mall
    path: /home/dev/projects/mall-backend
    workspace: mall
```

## 实现计划

| 阶段 | 任务 | 状态 |
|------|------|------|
| 1 | 创建 WorkspaceManager 类 | ✅ 完成 |
| 2 | 编写测试用例 | ✅ 14/14 通过 |
| 3 | 修改 insert_custom_kg 端点 | ✅ 完成 |
| 4 | 集成到 lightrag_server.py | 待部署时启用 |
| 5 | 部署到 H200 验证 | - |

## 相关文档

- [多项目部署指南](../deployment/MULTI_PROJECT_GUIDE.md)
- [运维手册](../deployment/OPERATIONS_MANUAL.md)
- [insert_custom_kg API](./INSERT_CUSTOM_KG_API.md)
