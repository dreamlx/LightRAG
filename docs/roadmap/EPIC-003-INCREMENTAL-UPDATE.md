# Epic: Incremental Update (Cold Rebuild → Incremental Rebuild)

**Epic ID**: EPIC-003
**创建日期**: 2026-02-21
**状态**: 🚧 Feature 1 完成, Feature 2/3 待开始
**涉及仓库**: codeindex, LoomGraph, LightRAG

---

## 背景

### 当前架构（Cold Rebuild, ADR-003）

每次代码变动，需要全量重建整个 workspace：

```
git pull → codeindex scan-all → loomgraph inject --full → DELETE /graph/clear → POST /insert_custom_kg
```

**问题**：

| 指标 | 当前 (Cold Rebuild) | 目标 (Incremental) |
|------|--------------------|--------------------|
| 1% 代码变动的重建范围 | 100% | ~1-5% |
| 重建耗时（中型项目 ~500 文件） | 分钟级 | 秒级 |
| Embedding API 调用 | 全量 | 仅变动部分 |
| 适用场景 | 首次索引、分支切换 | 日常开发迭代 |

### 为什么现在可行

1. `insert_custom_kg` 按 `source_id` 关联所有数据（entities, relations, chunks）
2. PG 后端支持按条件精确删除
3. codeindex 按文件粒度输出 ParseResult，天然支持差异检测

---

## 架构设计

### 核心思路

```
git diff HEAD~1 → affected files → delete by source_id → re-inject affected only
```

### 数据流

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│  codeindex   │     │  LoomGraph   │     │    LightRAG      │
│              │     │              │     │                  │
│ git diff     │────>│ diff-inject  │────>│ DELETE by source │
│ parse affected│    │ (affected    │     │ POST insert_kg   │
│ files only   │     │  files only) │     │ (affected only)  │
└─────────────┘     └─────────────┘     └──────────────────┘
```

### 三层变动检测

| 层次 | 责任方 | 机制 |
|------|--------|------|
| 文件级 | codeindex / LoomGraph | `git diff --name-only` 获取变动文件列表 |
| 符号级（未来） | codeindex | AST diff，跳过仅格式变动的文件 |
| 图谱级（未来） | LoomGraph | 比较新旧 ParseResult，跳过语义未变的实体 |

**Phase 1 只做文件级**，已覆盖绝大多数场景。符号级和图谱级是优化，不是必须。

---

## Feature 列表

### Feature 1: DELETE /graph/by_source 端点 (LightRAG)

**优先级**: P0
**状态**: ✅ 已完成

按 `source_id` 批量删除实体、关系、chunks，支持 workspace 路由。

**API 设计**：

```
DELETE /graph/by_source
Header: LIGHTRAG-WORKSPACE: <workspace>
Body: {"source_ids": ["src/main.py", "src/utils.py"]}
```

**Response**:
```json
{
  "status": "success",
  "workspace": "loomgraph_demo",
  "deleted": {
    "entities": 15,
    "relations": 23,
    "chunks": 8
  }
}
```

**实现要点**：
- 在 PG 中，entities/relations/chunks 都有 `source_id` 字段
- 需要同时清理 KV 存储、向量存储、图存储中的对应数据
- 图存储中的边删除需要考虑：如果一条边的两端实体来自不同 source_id，只删关系不删实体

#### Stories

| Story ID | 标题 | 估点 | 状态 |
|----------|------|------|------|
| S1.0 | 修复 `ainsert_custom_kg` 的 source_id 映射 | 1 | ✅ |
| S1.1 | 调研 PG 各存储表的 source_id 字段覆盖情况 | 2 | ✅ |
| S1.2 | 实现 `adelete_by_source_ids()` 在 LightRAG 类 | 5 | ✅ |
| S1.3 | 添加 `DELETE /graph/by_source` API 端点 | 2 | ✅ |
| S1.4 | 编写集成测试（inject → delete → verify） | 3 | 🔲 |

---

### Feature 2: loomgraph update 命令 (LoomGraph)

**优先级**: P0
**状态**: 🔲 待开始

增量更新命令，替代全量 `inject --full`。

```bash
# 增量更新（检测 git diff，只处理变动文件）
loomgraph update --workspace loomgraph_demo

# 指定基准 commit
loomgraph update --workspace loomgraph_demo --since HEAD~3

# 强制全量重建（等价于当前 Cold Rebuild）
loomgraph update --workspace loomgraph_demo --full
```

**流程**：
1. `git diff --name-only <since>..HEAD` → 变动文件列表
2. 过滤出支持的代码文件（按 codeindex 配置）
3. `codeindex scan` 仅处理变动文件 → ParseResult
4. `DELETE /graph/by_source` 删除旧数据
5. `POST /insert_custom_kg` 注入新数据

#### Stories

| Story ID | 标题 | 估点 | 状态 |
|----------|------|------|------|
| S2.1 | 实现 git diff 变动文件检测 | 2 | 🔲 |
| S2.2 | codeindex 支持指定文件列表的 scan | 2 | 🔲 |
| S2.3 | 实现 update 命令编排逻辑 | 3 | 🔲 |
| S2.4 | 端到端测试（修改文件 → update → query 验证） | 3 | 🔲 |

---

### Feature 3: 删除文件的处理 (LoomGraph)

**优先级**: P1
**状态**: 🔲 待开始

`git diff` 中的 deleted files 需要从图谱中移除，但不需要 re-inject。

**流程**：
1. `git diff --diff-filter=D` → 已删除文件列表
2. `DELETE /graph/by_source` 删除对应数据
3. 不调用 codeindex（文件已不存在）

#### Stories

| Story ID | 标题 | 估点 | 状态 |
|----------|------|------|------|
| S3.1 | 在 update 流程中处理 deleted/renamed 文件 | 2 | 🔲 |
| S3.2 | 测试删除场景 | 2 | 🔲 |

---

## 不在本 Epic 范围内

以下方向有价值，但属于未来优化，当前阶段不做：

| 方向 | 原因 |
|------|------|
| 多分支版本管理（branch_bitmap） | 用户量不支持；当前一个 workspace = 一个分支，Cold Rebuild 切换即可 |
| 分层存储（L1/L2/L3） | 数据量 ~10MB 级别，无需分层 |
| Graph-Diff 协议 | 需要 compare 功能上线后有真实性能数据再设计 |
| 符号级 AST diff | Phase 1 文件级已覆盖 80%+ 场景，符号级是优化 |
| 孤岛节点清理（Graph Janitor） | codeindex 确定性提取，删除 source_id 即精确，无孤岛问题 |

---

## 里程碑

| 阶段 | 目标 | Features |
|------|------|----------|
| Phase 1 | LightRAG 侧：按 source_id 删除能力 | Feature 1 |
| Phase 2 | LoomGraph 侧：update 命令 | Feature 2, 3 |
| Phase 3 | 生产验证 | 在 trial 实例上验证 |

---

## 技术决策记录

### ADR-005: 文件级增量，不做符号级

**决策**: Phase 1 以文件为最小更新粒度，不做符号级 AST diff。

**原因**:
1. 文件级检测通过 `git diff` 零成本获得
2. 覆盖日常开发 80%+ 的变动场景
3. 符号级需要 codeindex 缓存上一次 ParseResult 做对比，增加复杂度
4. 单文件的重新解析 + 重新注入耗时极低（毫秒级），不值得优化

**约束**:
- 当一个大文件（>1000 行）仅修改一行时，会重新注入该文件的所有实体/关系
- 可接受：这种场景的额外成本 < 1 秒

---

## 与 EPIC-001 的关系

EPIC-001 Feature 2（Upsert）和 Feature 3（按文件删除）是 pre-PG 时代的设计。
本 Epic 基于当前架构（PG + workspace routing + insert_custom_kg）重新规划，取代 EPIC-001 中未完成的部分。

---

## 相关文档

- [LoomGraph API Reference](../features/LOOMGRAPH_API.md)
- [ADR-003: Cold Rebuild](EPIC-002-POSTGRESQL-MIGRATION.md)
- [ADR-004: Per-customer PG](EPIC-002-POSTGRESQL-MIGRATION.md)
