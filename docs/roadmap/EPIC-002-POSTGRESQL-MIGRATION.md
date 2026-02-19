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
- Embedding 服务：TEI (Jina Code V2) 共享

### 问题
| 问题 | 影响 |
|------|------|
| Workspace 发现 | 只能扫目录，无法高效查询统计 |
| 并发安全 | 文件锁，多进程写入风险 |
| 内存占用 | 每个 workspace 的完整 graph 加载到内存 |
| 数据查询 | 无法执行 SQL 级别的聚合/过滤 |
| 水平扩展 | 单机文件系统，无法多实例共享 |

### 目标架构

```
客户 A (拼便宜):
  LightRAG :9610 → PG-A :5432 → TEI (Jina Code V2) :8090
                                        ↑ 共享

客户 B (智采云链):
  LightRAG :9620 → PG-B :5433 → TEI (Jina Code V2) :8090

未来 (如有非代码场景客户):
  LightRAG :9630 → PG-C :5434 → TEI-doc (BGE-M3) :8091
```

---

## 架构决策

### ADR-002: 分阶段迁移，文件版先行

**决策**: 先实现文件版 workspace 端点，再并行迁移 PG。

**原因**:
1. LoomGraph EPIC-005 阻塞于 workspace 列表端点
2. PG 迁移工作量大，不应阻塞下游开发
3. 端点接口设计一致，后端切换对调用方透明

### ADR-003: 不迁移数据，直接 Cold Rebuild

**决策**: 切换 PG 后不迁移 NetworkX 数据，由客户执行 Cold Rebuild。

**原因**:
1. 知识图谱本身就是 `loomgraph index` 的产物，随时可重建
2. 避免复杂的跨存储格式数据迁移
3. Cold Rebuild 确保数据在新后端的完整性和一致性

**影响**: Phase 3 从"数据迁移"简化为"配置切换 + Cold Rebuild"

### ADR-004: 每客户独立 PG 容器

**决策**: 每个客户部署独立的 PostgreSQL 容器，不共享。

**原因**:

| 维度 | 共享 PG | 独立 PG (选择) |
|------|---------|----------------|
| 数据隔离 | workspace 列过滤，应用层隔离 | 物理隔离，无泄漏可能 |
| 故障影响 | 一个客户的慢查询/死锁影响所有人 | 故障隔离 |
| 资源控制 | 难以限制单个客户的资源占用 | docker `--memory` / `--cpus` 独立限制 |
| 备份恢复 | 整库备份/恢复，粒度粗 | 按客户独立备份/恢复 |
| 运维复杂度 | 低 (1 个实例) | 中等 (N 个实例) |
| 资源开销 | 低 | 每个 PG ~50-100MB 内存 |

**适用规模**: 2-10 个客户。如果未来到 50+ 客户，可考虑共享 PG + schema 隔离。

**部署拓扑**:
```
docker-compose.customer-a.yml:
  pg-a:
    image: pgvector/pgvector:pg17
    ports: ["5432:5432"]
    volumes: [pg-a-data:/var/lib/postgresql/data]

  lightrag-a:
    environment:
      - POSTGRES_HOST=pg-a
      - POSTGRES_PORT=5432

docker-compose.customer-b.yml:
  pg-b:
    image: pgvector/pgvector:pg17
    ports: ["5433:5432"]
    volumes: [pg-b-data:/var/lib/postgresql/data]

  lightrag-b:
    environment:
      - POSTGRES_HOST=pg-b
      - POSTGRES_PORT=5432
```

### ADR-005: Embedding 模型默认共享，架构预留切换

**决策**: 所有客户默认共享 Jina Code V2，但架构支持按客户切换。

**当前**: 所有客户都是 LoomGraph 代码分析场景 → 共享同一个 TEI 实例

**预留能力**: 每个客户的 `.env` 独立配置 embedding endpoint，如有非代码场景客户可指向不同 TEI：

| 场景 | Embedding 模型 | TEI 实例 |
|------|----------------|----------|
| 代码分析 (默认) | Jina Code V2 | TEI :8090 (共享) |
| 文档 RAG (未来) | BGE-M3 | TEI-doc :8091 (新增) |
| 多语言 (未来) | multilingual-e5 | TEI-ml :8092 (新增) |

**注意**: 切换 embedding 模型 = 向量维度变化 = 必须 Cold Rebuild

---

## 迁移策略

### Phase 1: 文件版 Workspace 端点 ✅

先实现文件存储版的 `GET /api/workspaces`，解除 LoomGraph EPIC-005 阻塞。

**交付物**: `GET /api/workspaces` 返回 workspace 名称列表
**状态**: ✅ 已完成并部署

### Phase 2: PG 环境搭建

在 H200 上为每个客户部署独立 PG + pgvector 容器。

**交付物**:
- 每客户独立的 docker-compose 配置
- PG 连接测试通过
- `.env` 模板更新

### Phase 3: 存储后端切换

修改客户 `.env` 指向各自的 PG，执行 Cold Rebuild。

**交付物**:
- 客户 `.env` 配置（PG 连接参数）
- Cold Rebuild 操作手册
- 回滚方案（保留 NetworkX 文件，必要时切回）

### Phase 4: PG 版端点增强

利用 PG 能力增强 workspace 端点（统计、搜索等）。

**交付物**: `GET /api/workspaces` 返回带 entity_count/relation_count 的完整响应

---

## Feature 列表

### Feature 1: Workspace 列表端点 - 文件版 (Phase 1) ✅

**优先级**: P0 - 阻塞 LoomGraph
**文档**: [WORKSPACE_LIST_API.md](../features/WORKSPACE_LIST_API.md)
**状态**: ✅ 已完成

| Story | 标题 | 状态 |
|-------|------|------|
| S1.1 | 实现 workspace 目录扫描 | ✅ |
| S1.2 | 添加 GET /api/workspaces 端点 | ✅ |
| S1.3 | 编写测试 (6/6 passed) | ✅ |

### Feature 2: PostgreSQL 环境部署 (Phase 2)

**优先级**: P1
**状态**: 🔲 待开始

| Story | 标题 | 状态 |
|-------|------|------|
| S2.1 | 编写客户级 docker-compose (PG + pgvector) | 🔲 |
| S2.2 | 部署拼便宜 PG 容器 (port 5432) | 🔲 |
| S2.3 | 部署智采云链 PG 容器 (port 5433) | 🔲 |
| S2.4 | 验证 LightRAG PG 后端连通性 | 🔲 |

### Feature 3: 存储后端切换 (Phase 3)

**优先级**: P1
**状态**: 🔲 待开始

| Story | 标题 | 状态 |
|-------|------|------|
| S3.1 | 更新客户 .env (PG 连接参数) | 🔲 |
| S3.2 | 拼便宜 Cold Rebuild 验证 | 🔲 |
| S3.3 | 智采云链 Cold Rebuild 验证 | 🔲 |
| S3.4 | 编写回滚方案文档 | 🔲 |

### Feature 4: Workspace 端点增强 - PG 版 (Phase 4)

**优先级**: P2
**状态**: 🔲 待开始

| Story | 标题 | 状态 |
|-------|------|------|
| S4.1 | 实现 PG 版 workspace 列表 (带统计) | 🔲 |
| S4.2 | 添加 workspace 搜索/过滤 | 🔲 |

---

## H200 端口规划 (迁移后)

| 服务 | 拼便宜 | 智采云链 | 说明 |
|------|--------|----------|------|
| LightRAG | 9610 | 9620 | 不变 |
| PostgreSQL | 5432 | 5433 | 新增，独立容器 |
| Nginx 映射 | 3010/3001 | 3020 | 不变 |
| TEI | 8090 | 8090 | 共享 Jina Code V2 |

---

## 相关文档

- [LoomGraph API 需求](https://github.com/user/LoomGraph/docs/api/LIGHTRAG-WORKSPACE-API-REQUEST.md)
- [Workspace Manager](../features/WORKSPACE_MANAGER.md)
- [Workspace List API](../features/WORKSPACE_LIST_API.md)
- [EPIC-001: LoomGraph 集成](./EPIC-LOOMGRAPH-INTEGRATION.md)
- [运维手册](../deployment/OPERATIONS_MANUAL.md)
