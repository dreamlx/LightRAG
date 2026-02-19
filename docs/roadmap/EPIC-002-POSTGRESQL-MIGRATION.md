# Epic: PostgreSQL 存储后端迁移

**Epic ID**: EPIC-002
**版本**: TBD
**创建日期**: 2026-02-19
**状态**: 📋 规划中

---

## 背景

### 当前架构
- 存储后端：NetworkX (文件存储)
- 每个 workspace = `rag_storage/` 下的子目录
- 数据持久化：GraphML 文件 + JSON KV 存储

### 问题
| 问题 | 影响 |
|------|------|
| Workspace 发现 | 只能扫目录，无法高效查询统计 |
| 并发安全 | 文件锁，多进程写入风险 |
| 内存占用 | 每个 workspace 的完整 graph 加载到内存 |
| 数据查询 | 无法执行 SQL 级别的聚合/过滤 |
| 水平扩展 | 单机文件系统，无法多实例共享 |

### 目标架构
- 存储后端：PostgreSQL + pgvector
- workspace 隔离：`workspace` 列过滤（已有表设计支持）
- 连接池：多 workspace 共享，按需查询
- 统计查询：SQL 即时返回

---

## 迁移策略

### Phase 1: 文件版 Workspace 端点 (立即)

先实现文件存储版的 `GET /api/workspaces`，解除 LoomGraph EPIC-005 阻塞。

**交付物**: `GET /api/workspaces` 返回 workspace 名称列表
**状态**: 🔄 进行中

### Phase 2: PG 环境搭建 (并行)

在 H200 上部署 PostgreSQL + pgvector，验证连通性。

**交付物**: docker-compose 配置、连接测试通过

### Phase 3: 存储后端切换

修改 `.env` 配置切换到 PG 后端，迁移现有数据。

**交付物**: 数据迁移脚本、回滚方案

### Phase 4: PG 版端点增强

利用 PG 能力增强 workspace 端点（统计、搜索等）。

**交付物**: `GET /api/workspaces` 返回带 entity_count/relation_count 的完整响应

---

## Feature 列表

### Feature 1: Workspace 列表端点 - 文件版 (Phase 1)

**优先级**: P0 - 阻塞 LoomGraph
**文档**: [WORKSPACE_LIST_API.md](../features/WORKSPACE_LIST_API.md)

| Story | 标题 | 状态 |
|-------|------|------|
| S1.1 | 实现 workspace 目录扫描 | 🔲 |
| S1.2 | 添加 GET /api/workspaces 端点 | 🔲 |
| S1.3 | 编写测试 | 🔲 |

### Feature 2: PostgreSQL 环境部署 (Phase 2)

**优先级**: P1
**状态**: 🔲 待开始

| Story | 标题 | 状态 |
|-------|------|------|
| S2.1 | docker-compose 添加 PG + pgvector | 🔲 |
| S2.2 | 配置 LightRAG PG 连接参数 | 🔲 |
| S2.3 | 验证 PG 后端基本功能 | 🔲 |

### Feature 3: 数据迁移 (Phase 3)

**优先级**: P1
**状态**: 🔲 待开始

| Story | 标题 | 状态 |
|-------|------|------|
| S3.1 | 编写 NetworkX → PG 迁移脚本 | 🔲 |
| S3.2 | 验证数据完整性 | 🔲 |
| S3.3 | 编写回滚方案 | 🔲 |

### Feature 4: Workspace 端点增强 - PG 版 (Phase 4)

**优先级**: P2
**状态**: 🔲 待开始

| Story | 标题 | 状态 |
|-------|------|------|
| S4.1 | 实现 PG 版 workspace 列表 (带统计) | 🔲 |
| S4.2 | 添加 workspace 搜索/过滤 | 🔲 |

---

## 技术决策

### ADR-002: 分阶段迁移，文件版先行

**决策**: 先实现文件版 workspace 端点，再并行迁移 PG。

**原因**:
1. LoomGraph EPIC-005 阻塞于 workspace 列表端点
2. PG 迁移工作量大，不应阻塞下游开发
3. 端点接口设计一致，后端切换对调用方透明

---

## 相关文档

- [LoomGraph API 需求](https://github.com/user/LoomGraph/docs/api/LIGHTRAG-WORKSPACE-API-REQUEST.md)
- [Workspace Manager](../features/WORKSPACE_MANAGER.md)
- [EPIC-001: LoomGraph 集成](./EPIC-LOOMGRAPH-INTEGRATION.md)
