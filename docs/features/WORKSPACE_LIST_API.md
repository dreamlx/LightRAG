# Feature: GET /api/workspaces Endpoint

## 概述

新增 HTTP 端点返回所有已存在的 workspace 列表，支持 LoomGraph 的 workspace 管理功能。

## 背景

**请求方**: LoomGraph EPIC-005 (Workspace Management)
**阻塞**: LoomGraph 需要发现服务器上的 workspace 列表

当前 `WorkspaceManager.list_workspaces()` 只返回内存中已加载的实例，无法发现未加载的 workspace。

## API 规格

### 端点

```
GET /api/workspaces
```

### 响应

```json
{
  "workspaces": ["default", "erp", "crm"],
  "count": 3
}
```

### 认证

与现有端点一致（API Key / Basic Auth）。

### 特殊说明

- **不需要** `LIGHTRAG-WORKSPACE` header（查询所有 workspace）
- 文件存储版：扫描 `working_dir` 下的子目录
- 未来 PG 版：`SELECT DISTINCT workspace FROM LIGHTRAG_DOC_STATUS`

## 实现（文件存储版）

### 1. WorkspaceManager 新增方法

```python
def discover_workspaces(self) -> list[str]:
    """扫描 working_dir 下的所有 workspace 目录."""
    workspaces = []
    working_path = Path(self._working_dir)
    if working_path.exists():
        for entry in sorted(working_path.iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                workspaces.append(entry.name)
    return workspaces
```

### 2. HTTP 端点

```python
@router.get("/api/workspaces")
async def list_all_workspaces():
    return {
        "workspaces": workspace_manager.discover_workspaces(),
        "count": len(workspaces),
    }
```

## 测试用例

| TC | 场景 | 期望 |
|----|------|------|
| 01 | 空 working_dir | `{"workspaces": [], "count": 0}` |
| 02 | 有 workspace 目录 | 返回目录名列表 |
| 03 | 包含隐藏目录 (.xxx) | 忽略隐藏目录 |
| 04 | 包含文件（非目录） | 忽略文件 |
| 05 | 已加载 + 未加载混合 | 都返回 |

## 验收标准

- [ ] 端点返回所有 workspace 目录
- [ ] 忽略隐藏目录和文件
- [ ] 认证正常工作
- [ ] 所有测试通过

## 未来增强 (PG 版)

PG 迁移后升级为带统计的响应：

```json
{
  "workspaces": [
    {"name": "erp", "entity_count": 245, "relation_count": 1024},
    {"name": "crm", "entity_count": 89, "relation_count": 312}
  ],
  "count": 2
}
```

## 相关文档

- [EPIC-002: PostgreSQL 迁移](../roadmap/EPIC-002-POSTGRESQL-MIGRATION.md)
- [LoomGraph API 需求](https://github.com/user/LoomGraph/docs/api/LIGHTRAG-WORKSPACE-API-REQUEST.md)
- [Workspace Manager](./WORKSPACE_MANAGER.md)
