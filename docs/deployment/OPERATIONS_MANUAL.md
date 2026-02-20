# LightRAG 运维手册

本文档记录 LightRAG 多租户部署的运维操作指南。

## 生态系统

三仓库分层架构：

| 仓库 | 职责 | GitHub |
|------|------|--------|
| **codeindex** | AST 解析，提取代码结构 (Symbol/Call/Inheritance/Import) | https://github.com/dreamlx/codeindex |
| **LoomGraph** | 协调调度，数据映射，CLI/MCP 入口 | https://github.com/dreamlx/LoomGraph |
| **LightRAG** | 存储检索，知识图谱管理 (PG + pgvector + AGE) | https://github.com/dreamlx/LightRAG (fork of HKUDS/LightRAG) |

```
codeindex scan → ParseResult JSON → LoomGraph embed/inject → LightRAG API → PostgreSQL
```

架构详情: [LoomGraph SYSTEM_DESIGN.md](https://github.com/dreamlx/LoomGraph/blob/main/docs/architecture/SYSTEM_DESIGN.md)

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端调用链                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   codeindex (CLI)  →  LoomGraph (CLI)  →  LightRAG (API)       │
│      独立工具           调度编排            存储服务             │
│                                                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      H200 服务器架构                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   外部访问 (端口 3000-3499)                                     │
│          │                                                      │
│          ├── :3000  GLM-4.7-fp8 (New API → SGLang)             │
│          ├── :3002  TEI Embedding (共享)                        │
│          ├── :3010  拼便宜 LightRAG                             │
│          ├── :3020  智采云链 LightRAG                           │
│          └── :3030  试用 LightRAG                               │
│                     │                                           │
│                     ▼                                           │
│                  Nginx                                          │
│                     │                                           │
│          ┌─────────┼─────────┐                                 │
│          ▼         ▼         ▼                                  │
│   :9610       :9620       :9630                                 │
│   LightRAG    LightRAG    LightRAG                              │
│  (pinpianyi) (zhicaiyunlian) (trial)                            │
│          │         │         │                                  │
│          ▼         ▼         ▼                                  │
│   :5432 PG    :5433 PG    :5434 PG                              │
│   (独立)      (独立)      (共享/试用)                           │
│          │         │         │                                  │
│          └─────────┼─────────┘                                 │
│                    ▼                                            │
│          :9624 TEI (GPU 4)                                      │
│          :3000 GLM-4.7 (共享)                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 服务端点

### 对外服务

| 公司 | 项目 | 外部端口 | URL | 用途 |
|------|------|----------|-----|------|
| 拼便宜 | default | 3010 | `http://117.131.45.179:3010` | 代码知识图谱 |
| 拼便宜 | default | 3001 | `http://117.131.45.179:3001` | ⚠️ 旧端口 (向后兼容) |
| 智采云链 | default | 3020 | `http://117.131.45.179:3020` | 代码知识图谱 |
| 试用 | trial | 3030 | `http://117.131.45.179:3030` | 试用/Demo (多 workspace 共享 PG) |
| (共享) | TEI | 3002 | `http://117.131.45.179:3002` | Embedding 服务 |
| (共享) | LLM | 3000 | `http://117.131.45.179:3000` | GLM-4.7-fp8 |

### 内部服务

| 服务 | 内部端口 | 说明 |
|------|----------|------|
| pinpianyi_default | 9610 | 拼便宜 LightRAG |
| zhicaiyunlian_default | 9620 | 智采云链 LightRAG |
| trial_default | 9630 | 试用 LightRAG (多 workspace 共享 PG) |
| TEI | 9624 | Jina Code V2 Embedding |
| pg-pinpianyi | 5432 | 拼便宜 PostgreSQL (pgvector + AGE) |
| pg-zhicaiyunlian | 5433 | 智采云链 PostgreSQL (pgvector + AGE) |
| pg-trial | 5434 | 试用 PostgreSQL (多 workspace 共享) |
| postgres (new-api) | - | New API 内部数据库 (Docker 网络) |
| Redis | 6379 | 缓存 (New API 内部) |

### 端口规划

```
3000       : GLM-4.7 LLM (New API) - 共享
3001       : 拼便宜 (旧端口, 向后兼容)
3002       : TEI Embedding - 共享
3010-3019  : 拼便宜 项目组
3020-3029  : 智采云链 项目组
3030       : 试用 Trial (多 workspace 共享 PG)
3031-3039  : 预留 (新客户)
3040-3049  : 预留
5432       : 拼便宜 PostgreSQL
5433       : 智采云链 PostgreSQL
5434       : 试用 PostgreSQL (多 workspace 共享)
5435+      : 预留 (新客户 PostgreSQL)
...
```

## 目录结构

```
~/lightrag/                    # LightRAG 代码库
├── .venv/                     # Python 虚拟环境
└── lightrag/                  # 源码

/root/pg-data/                 # PostgreSQL 数据 & 配置
├── docker-compose.yml         # PG 容器编排
├── pinpianyi/                 # 拼便宜 PG 数据
├── zhicaiyunlian/             # 智采云链 PG 数据
└── trial/                     # 试用 PG 数据 (多 workspace 共享)

~/lightrag-projects/           # 项目数据目录
├── pinpianyi_default/
│   ├── .env                   # 项目配置
│   ├── rag_storage/           # LLM 缓存 (图谱数据已迁移至 PG)
│   ├── inputs/                # 输入文件
│   └── lightrag.log           # 日志
├── zhicaiyunlian_default/
│   ├── .env
│   ├── rag_storage/
│   ├── inputs/
│   └── lightrag.log
├── start-instance.sh          # 启动单个实例
├── stop-instance.sh           # 停止单个实例
├── start-all.sh               # 启动全部
├── stop-all.sh                # 停止全部
└── status.sh                  # 查看状态
```

## 日常运维

### 查看服务状态

```bash
# 查看所有 LightRAG 实例状态
~/lightrag-projects/status.sh

# 查看 Docker 容器状态 (TEI, New API, etc.)
docker ps

# 查看特定实例日志
tail -f ~/lightrag-projects/pinpianyi_default/lightrag.log
tail -f ~/lightrag-projects/zhicaiyunlian_default/lightrag.log

# 查看 TEI 日志
docker logs -f tei-jina
```

### 代码更新部署

```bash
# 方式一: Git Pull (需要网络访问 GitHub)
cd ~/lightrag
git pull origin loomgraph-main
~/lightrag-projects/stop-all.sh
~/lightrag-projects/start-all.sh

# 方式二: SCP 传输 (GitHub 不可达时)
# 在本地执行:
scp -P 2213 lightrag/api/routers/document_routes.py \
  root@117.131.45.179:~/lightrag/lightrag/api/routers/

# 在服务器执行:
~/lightrag-projects/stop-all.sh && ~/lightrag-projects/start-all.sh
```

**注意**: 代码库共享，更新一份代码后重启，所有客户实例生效。

### 启动/停止服务

```bash
# 启动单个实例
~/lightrag-projects/start-instance.sh pinpianyi_default
~/lightrag-projects/start-instance.sh zhicaiyunlian_default

# 停止单个实例
~/lightrag-projects/stop-instance.sh pinpianyi_default

# 启动/停止全部
~/lightrag-projects/start-all.sh
~/lightrag-projects/stop-all.sh

# 重启 TEI
docker restart tei-jina

# PostgreSQL 管理 (docker-compose)
cd /root/pg-data
docker compose ps          # 查看状态
docker compose restart     # 重启全部 PG
docker compose logs -f     # 查看日志

# 重载 Nginx
systemctl reload nginx
```

### 健康检查

```bash
# 检查各服务健康状态
curl -s http://localhost:3010/health | jq '.status'  # 拼便宜
curl -s http://localhost:3020/health | jq '.status'  # 智采云链
curl -s http://localhost:3002/health                  # TEI
curl -s http://localhost:3000/v1/models              # LLM
```

## 新增客户

### 1. 创建项目目录

```bash
# 格式: {company}_{project}
COMPANY=newclient
PROJECT=default
WORKSPACE=${COMPANY}_${PROJECT}
PORT=9630  # 选择未使用的端口

mkdir -p ~/lightrag-projects/${WORKSPACE}/{rag_storage,inputs}
```

### 2. 创建配置文件

```bash
cat > ~/lightrag-projects/${WORKSPACE}/.env << EOF
# ${COMPANY} - ${PROJECT}
WORKSPACE=${WORKSPACE}
PORT=${PORT}
HOST=0.0.0.0

# LLM 配置
LLM_BINDING=openai
LLM_MODEL=glm-4.7-fp8
LLM_BINDING_HOST=http://localhost:3000/v1
LLM_BINDING_API_KEY=sk-your-api-key-here
OPENAI_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
OPENAI_LLM_MAX_TOKENS=9000

# Embedding 配置
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=jinaai/jina-embeddings-v2-base-code
EMBEDDING_DIM=768
EMBEDDING_SEND_DIM=false
EMBEDDING_TOKEN_LIMIT=8192
EMBEDDING_BINDING_HOST=http://localhost:9624/v1
EMBEDDING_BINDING_API_KEY=dummy

# 其他
ENABLE_LLM_CACHE=true
ENABLE_LLM_CACHE_FOR_EXTRACT=true
MAX_ASYNC=4
MAX_PARALLEL_INSERT=2

# PostgreSQL Storage Backend
LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_GRAPH_STORAGE=PGGraphStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage

POSTGRES_HOST=localhost
POSTGRES_PORT=5434  # 选择未使用的 PG 端口
POSTGRES_USER=lightrag
POSTGRES_PASSWORD=lightrag_${COMPANY}_2026
POSTGRES_DATABASE=lightrag
POSTGRES_MAX_CONNECTIONS=20
POSTGRES_ENABLE_VECTOR=true
EOF
```

### 3. 添加 PG 容器

编辑 `/root/pg-data/docker-compose.yml`，添加新服务:

```yaml
  pg-newclient:
    image: marcosbolanos/pgvector-age:latest
    container_name: pg-newclient
    restart: unless-stopped
    environment:
      POSTGRES_USER: lightrag
      POSTGRES_PASSWORD: lightrag_newclient_2026
      POSTGRES_DB: lightrag
    ports:
      - '5434:5432'
    volumes:
      - /root/pg-data/newclient:/var/lib/postgresql/data
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U lightrag']
      interval: 10s
      timeout: 5s
      retries: 5
```

```bash
mkdir -p /root/pg-data/newclient
cd /root/pg-data && docker compose up -d
```

### 4. 添加 Nginx 配置

编辑 `/etc/nginx/sites-available/lightrag`，添加：

```nginx
# ${COMPANY} - ${PROJECT}
# External: 30X0 -> Internal: 96X0
server {
    listen 3030;  # 根据端口规划选择
    server_name _;
    client_max_body_size 200M;
    proxy_read_timeout 300s;
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:9630;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 5. 启动服务

```bash
# 重载 Nginx
nginx -t && systemctl reload nginx

# 启动实例
~/lightrag-projects/start-instance.sh ${WORKSPACE}

# 验证
curl http://localhost:3030/health
```

## LoomGraph 集成指南

### API 端点

LoomGraph 通过 HTTP REST API 与 LightRAG 交互：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/insert_custom_kg` | POST | 插入代码知识图谱 (跳过 LLM) |
| `/query` | POST | 查询知识图谱 |
| `/documents/text` | POST | 插入文本 (完整 LLM 流程) |
| `/documents` | DELETE | 清空全部数据 (用于重建) |
| `/documents/delete_entity` | DELETE | 删除单个实体及其关系 |
| `/documents/clear_cache` | DELETE | 清空 LLM 响应缓存 |

### 插入代码知识图谱

**请求格式:**

```bash
curl -X POST http://117.131.45.179:3020/insert_custom_kg \
  -H "Content-Type: application/json" \
  -d '{
    "custom_kg": {
      "chunks": [
        {
          "content": "def login(username, password): ...",
          "source_id": "auth.py:42",
          "file_path": "src/auth.py"
        }
      ],
      "entities": [
        {
          "entity_name": "AuthService.login",
          "entity_type": "method",
          "description": "用户登录验证方法",
          "source_id": "auth.py:42"
        }
      ],
      "relationships": [
        {
          "src_id": "AuthService.login",
          "tgt_id": "hashlib.sha256",
          "description": "调用 sha256 进行密码哈希",
          "keywords": "calls,dependency",
          "weight": 1.0
        }
      ]
    }
  }'
```

### 查询

```bash
curl -X POST http://117.131.45.179:3020/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "login 方法如何验证用户？",
    "mode": "hybrid"
  }'
```

### 更新策略

LoomGraph 采用 Warm/Cold 两层更新策略：

```
┌──────┬───────────────┬─────────────────────────────────┐
│ 层级 │   触发时机    │              操作               │
├──────┼───────────────┼─────────────────────────────────┤
│ Warm │ git commit    │ POST /insert_custom_kg (追加)   │
├──────┼───────────────┼─────────────────────────────────┤
│ Cold │ 凌晨 / 手动   │ DELETE /documents + 全量重建    │
└──────┴───────────────┴─────────────────────────────────┘
```

#### Warm Update (增量追加)

每次 `git commit` 后，LoomGraph 只处理变动文件，调用 `POST /insert_custom_kg` 追加到知识图谱。
旧版本实体仍存在，适合日常开发。

#### Cold Rebuild (全量重建)

定期清空并重建，清除过时数据：

```bash
# 1. 清空知识图谱
curl -X DELETE http://117.131.45.179:3010/documents

# 2. 全量重新索引
loomgraph index --full /path/to/repo
```

建议凌晨定时执行或手动触发。

## 试用实例

### 架构

试用客户共享一个 PG 实例 (`pg-trial:5434`)，通过 LightRAG workspace 隔离不同客户的数据。
付费客户则获得独立 PG 容器 + 独立显卡绑定。

```
试用 LightRAG :9630 (Nginx :3030)
      │
      ├── workspace: loomgraph_demo     ← 预装 demo (LoomGraph 仓库)
      ├── workspace: trial_customer_a   ← 试用客户 A
      └── workspace: trial_customer_b   ← 试用客户 B
      │
      ▼
  pg-trial :5434 (共享，workspace 列隔离)
```

| 维度 | 试用 | 付费 |
|------|------|------|
| PG | 共享 `pg-trial` | 独立容器 |
| LightRAG | 共享实例 :9630 | 独立实例 |
| GPU 绑定 | 共享 TEI | 独立显卡 |
| Demo 数据 | LoomGraph 仓库 | 客户自有仓库 |

### 试用 → 付费转化

1. 按 [新增客户](#新增客户) 流程为付费客户创建独立实例
2. 客户在新实例上执行 Cold Rebuild (全量重新索引)
3. 清理试用实例中该客户的 workspace 数据

## 故障排查

### 服务无法启动

```bash
# 检查端口占用
lsof -i :9620
ss -tlnp | grep 9620

# 检查日志
tail -100 ~/lightrag-projects/zhicaiyunlian_default/lightrag.log

# 手动启动调试
cd ~/lightrag
source .venv/bin/activate
WORKING_DIR=~/lightrag-projects/zhicaiyunlian_default/rag_storage \
INPUT_DIR=~/lightrag-projects/zhicaiyunlian_default/inputs \
PORT=9620 \
python -m lightrag.api.lightrag_server
```

### PostgreSQL 连接失败

```bash
# 检查 PG 容器状态
cd /root/pg-data && docker compose ps

# 检查 PG 日志
docker compose logs pg-pinpianyi --tail 50

# 手动连接测试
docker exec pg-pinpianyi psql -U lightrag -c "SELECT 1"

# 检查扩展
docker exec pg-pinpianyi psql -U lightrag -c "SELECT extname, extversion FROM pg_extension;"

# AGE 扩展缺失 (create_graph 报错)
docker exec pg-pinpianyi psql -U lightrag -c "CREATE EXTENSION IF NOT EXISTS age CASCADE;"

# 重启 PG
docker compose restart pg-pinpianyi
```

### Docker 无法启动新容器 (cgroup timeout)

**症状**: `Failed to activate service 'org.freedesktop.systemd1': timed out`

**原因**: Docker 默认使用 systemd cgroup driver，通过 D-Bus 请求 systemd 创建 cgroup scope。
当 systemd/D-Bus 通信卡住时，新容器无法启动（已运行的容器不受影响）。

**临时修复**: 切换到 cgroupfs driver，绕过 systemd 直接操作 cgroup 文件系统。

```bash
# 1. 停止当前 Docker
kill $(cat /var/run/docker.pid)
sleep 5

# 2. 用 cgroupfs driver 重启 (临时方案，不改 daemon.json)
nohup dockerd --exec-opt native.cgroupdriver=cgroupfs &>/tmp/dockerd.log &
sleep 15

# 3. 验证
docker ps  # 已有容器自动恢复 (restart policy)
```

**彻底修复**: 重启服务器。systemd 恢复后 Docker 会自动使用默认的 systemd driver。

**注意**: 不要将 cgroupfs 写入 `/etc/docker/daemon.json`。cgroupfs 与 systemd 同时管理 cgroup
可能产生冲突，仅作为 systemd 卡死时的临时绕过方案。

**2026-02-20 状态**: Docker 当前以 cgroupfs 模式手动运行中，等待下次维护窗口重启服务器。

### TEI 服务异常

```bash
# 查看 TEI 日志
docker logs tei-jina --tail 100

# 重启 TEI
docker restart tei-jina

# 检查 GPU 状态
nvidia-smi
```

### Nginx 502 错误

```bash
# 检查后端服务是否运行
curl http://localhost:9620/health

# 检查 Nginx 配置
nginx -t

# 查看 Nginx 错误日志
tail -100 /var/log/nginx/error.log
```

### 查询超时

```bash
# 检查 LLM 服务
curl http://localhost:3000/v1/models

# 检查 Embedding 服务
curl http://localhost:9624/health

# 增加超时时间 (修改 .env)
# LLM_TIMEOUT=300
```

## PostgreSQL 管理

### 架构决策

- **ADR-004**: 每客户独立 PG 容器 (物理隔离)
- **ADR-003**: Cold Rebuild (不迁移旧 NetworkX 数据)
- **镜像**: `marcosbolanos/pgvector-age:latest` (PG16 + pgvector 0.8.0 + AGE 1.5.0)
- **编排**: `/root/pg-data/docker-compose.yml`

### 密码规则

格式: `lightrag_{customer_shortname}_{year}`

| 客户 | 用户名 | 密码 | 端口 |
|------|--------|------|------|
| 拼便宜 | lightrag | lightrag_pinpianyi_2026 | 5432 |
| 智采云链 | lightrag | lightrag_zcyl_2026 | 5433 |
| 试用 | lightrag | lightrag_trial_2026 | 5434 |

### 常用操作

```bash
# 查看 PG 容器状态
cd /root/pg-data && docker compose ps

# 重启 PG
docker compose restart

# 查看 PG 日志
docker compose logs -f pg-pinpianyi

# 连接到 PG (拼便宜)
docker exec -it pg-pinpianyi psql -U lightrag

# 查看表
docker exec pg-pinpianyi psql -U lightrag -c '\dt'

# 查看扩展
docker exec pg-pinpianyi psql -U lightrag -c "SELECT extname, extversion FROM pg_extension;"

# 查看数据量
docker exec pg-pinpianyi psql -U lightrag -c "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
```

### 存储配置 (.env)

每个客户 .env 文件需要以下 PG 配置:

```bash
# Storage Backend
LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_GRAPH_STORAGE=PGGraphStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage

# PostgreSQL Connection
POSTGRES_HOST=localhost
POSTGRES_PORT=5432           # 每客户不同
POSTGRES_USER=lightrag
POSTGRES_PASSWORD=lightrag_xxx_2026
POSTGRES_DATABASE=lightrag
POSTGRES_MAX_CONNECTIONS=20
POSTGRES_ENABLE_VECTOR=true
```

### 回滚到 NetworkX

如果需要回退到文件存储:

```bash
# 1. 注释掉 .env 中的 LIGHTRAG_*_STORAGE 和 POSTGRES_* 行
# 2. 重启实例 (自动回退到 JsonKV + NanoVectorDB + NetworkX)
# 3. rag_storage/ 目录的文件数据仍在
```

### 新增客户 PG 容器

见 [新增客户 > Step 3](#3-添加-pg-容器)。

## 备份与恢复

### 备份数据

```bash
# 备份单个项目 (配置 + 文件数据)
tar -czf backup_pinpianyi_$(date +%Y%m%d).tar.gz \
  -C ~/lightrag-projects pinpianyi_default/

# 备份 PG 数据库
docker exec pg-pinpianyi pg_dump -U lightrag lightrag > backup_pg_pinpianyi_$(date +%Y%m%d).sql

# 备份所有项目
tar -czf backup_all_$(date +%Y%m%d).tar.gz \
  -C ~/lightrag-projects .
```

### 恢复数据

```bash
# 停止服务
~/lightrag-projects/stop-instance.sh pinpianyi_default

# 恢复文件数据
tar -xzf backup_pinpianyi_20240208.tar.gz -C ~/lightrag-projects/

# 恢复 PG 数据库
docker exec -i pg-pinpianyi psql -U lightrag lightrag < backup_pg_pinpianyi_20240208.sql

# 重启服务
~/lightrag-projects/start-instance.sh pinpianyi_default
```

## 监控建议

### 定期检查脚本

```bash
#!/bin/bash
# /root/scripts/check_lightrag.sh

# 检查所有 LightRAG 实例
for dir in ~/lightrag-projects/*/; do
    project=$(basename "$dir")
    if [ -f "$dir/.env" ]; then
        source "$dir/.env"
        if ! curl -s --max-time 5 http://localhost:$PORT/health > /dev/null; then
            echo "ALERT: $project on port $PORT is DOWN"
        fi
    fi
done

# 检查 PG 容器
for pg in pg-pinpianyi pg-zhicaiyunlian pg-trial; do
    if ! docker exec $pg pg_isready -U lightrag -q 2>/dev/null; then
        echo "ALERT: $pg is DOWN"
    fi
done
```

### Crontab 配置

```bash
# 每 5 分钟检查一次
*/5 * * * * /root/scripts/check_lightrag.sh >> /var/log/lightrag_monitor.log 2>&1

# 每天凌晨备份
0 3 * * * tar -czf /backup/lightrag_$(date +\%Y\%m\%d).tar.gz -C ~/lightrag-projects . 2>&1
```

## 变更记录

| 日期 | 变更内容 | 操作人 |
|------|----------|--------|
| 2026-02-08 | 初始部署：拼便宜、智采云链 | - |
| 2026-02-08 | 拼便宜数据从默认实例迁移到独立目录 | - |
| 2026-02-08 | 添加端口 3001 向后兼容 (指向拼便宜) | - |
| 2026-02-10 | 添加 LoomGraph Warm/Cold 更新策略文档 | - |
| 2026-02-10 | 部署 POST /insert_custom_kg 批量注入端点 | - |
| 2026-02-20 | PostgreSQL 迁移: 部署 pgvector+AGE 容器 (EPIC-002) | - |
| 2026-02-20 | 存储后端切换: NetworkX → PGGraphStorage, NanoVectorDB → PGVectorStorage | - |
| 2026-02-20 | Docker daemon 修复: systemd cgroup timeout, 临时切换到 cgroupfs driver | - |
| 2026-02-20 | 部署试用实例: pg-trial:5434, LightRAG:9630, Nginx:3030 (多 workspace 共享 PG) | - |
