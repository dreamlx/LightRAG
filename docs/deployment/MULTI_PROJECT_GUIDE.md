# 多项目部署指南

本文档说明如何为多个软件项目部署独立的代码知识图谱。

## 架构概述

```
LoomGraph (代码索引)
    │
    ├── 项目 A ──→ LightRAG 实例 A (:9631) ──→ Nginx (:3011)
    ├── 项目 B ──→ LightRAG 实例 B (:9632) ──→ Nginx (:3012)
    └── 项目 C ──→ LightRAG 实例 C (:9633) ──→ Nginx (:3013)
                         │
                         ▼
                   共享服务
                   ├── TEI Embedding (:9624 → :3002)
                   └── GLM-4.7 LLM (:3000)
```

## 方案一：多实例部署（当前推荐）

每个项目运行独立的 LightRAG 服务实例，通过不同端口区分。

### 优点
- 零代码修改，开箱即用
- 完全隔离，互不影响
- 可独立重启/升级

### 缺点
- 每个实例占用内存（约 200-500MB）
- 需要管理多个进程
- 端口分配需规划

### 部署步骤

#### 1. 创建项目目录结构

```bash
mkdir -p ~/lightrag-projects/{project_a,project_b,project_c}
```

#### 2. 为每个项目创建配置

```bash
# 项目 A
cat > ~/lightrag-projects/project_a/.env << 'EOF'
# 项目标识
WORKSPACE=project_a
PORT=9631

# LLM 配置 (共享)
LLM_BINDING=openai
LLM_MODEL=glm-4.7-fp8
LLM_BINDING_HOST=http://localhost:3000/v1
LLM_BINDING_API_KEY=<your-api-key>
OPENAI_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
OPENAI_LLM_MAX_TOKENS=9000

# Embedding 配置 (共享)
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=jinaai/jina-embeddings-v2-base-code
EMBEDDING_DIM=768
EMBEDDING_BINDING_HOST=http://localhost:9624/v1
EMBEDDING_BINDING_API_KEY=dummy
EOF

# 复制给其他项目，修改 WORKSPACE 和 PORT
cp ~/lightrag-projects/project_a/.env ~/lightrag-projects/project_b/.env
sed -i 's/project_a/project_b/; s/9631/9632/' ~/lightrag-projects/project_b/.env

cp ~/lightrag-projects/project_a/.env ~/lightrag-projects/project_c/.env
sed -i 's/project_a/project_c/; s/9631/9633/' ~/lightrag-projects/project_c/.env
```

#### 3. 创建启动脚本

```bash
cat > ~/lightrag-projects/start-all.sh << 'EOF'
#!/bin/bash
cd ~/lightrag

for project in project_a project_b project_c; do
    export $(grep -v '^#' ~/lightrag-projects/$project/.env | xargs)

    # 创建数据目录
    mkdir -p ~/lightrag-projects/$project/rag_storage
    mkdir -p ~/lightrag-projects/$project/inputs

    # 启动服务
    WORKING_DIR=~/lightrag-projects/$project/rag_storage \
    INPUT_DIR=~/lightrag-projects/$project/inputs \
    nohup .venv/bin/python -m lightrag.api.lightrag_server \
        > ~/lightrag-projects/$project/lightrag.log 2>&1 &

    echo "Started $project on port $PORT (PID: $!)"
done
EOF
chmod +x ~/lightrag-projects/start-all.sh
```

#### 4. 创建停止脚本

```bash
cat > ~/lightrag-projects/stop-all.sh << 'EOF'
#!/bin/bash
pkill -f "lightrag.api.lightrag_server"
echo "All LightRAG instances stopped"
EOF
chmod +x ~/lightrag-projects/stop-all.sh
```

#### 5. 配置 Nginx 反向代理

添加到 `/etc/nginx/sites-available/lightrag`:

```nginx
# 项目 A
server {
    listen 3011;
    server_name _;
    client_max_body_size 200M;
    proxy_read_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:9631;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# 项目 B
server {
    listen 3012;
    server_name _;
    client_max_body_size 200M;
    proxy_read_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:9632;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# 项目 C
server {
    listen 3013;
    server_name _;
    client_max_body_size 200M;
    proxy_read_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:9633;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

重载 Nginx:
```bash
nginx -t && systemctl reload nginx
```

### 端口规划

| 项目 | 内部端口 | 外部端口 | URL |
|------|----------|----------|-----|
| 共享 LLM | 3000 | 3000 | `http://<ip>:3000` |
| 共享 LightRAG (默认) | 9621 | 3001 | `http://<ip>:3001` |
| 共享 TEI | 9624 | 3002 | `http://<ip>:3002` |
| 项目 A | 9631 | 3011 | `http://<ip>:3011` |
| 项目 B | 9632 | 3012 | `http://<ip>:3012` |
| 项目 C | 9633 | 3013 | `http://<ip>:3013` |
| ... | 963x | 301x | ... |

### LoomGraph 调用示例

```python
import httpx

# 项目配置
PROJECTS = {
    "my-repo-a": "http://117.131.45.179:3011",
    "my-repo-b": "http://117.131.45.179:3012",
    "my-repo-c": "http://117.131.45.179:3013",
}

async def insert_code_kg(project_id: str, custom_kg: dict):
    """插入代码知识图谱到指定项目"""
    url = PROJECTS[project_id]
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{url}/insert_custom_kg",
            json=custom_kg
        )
        return response.json()

async def query(project_id: str, question: str, mode: str = "hybrid"):
    """查询指定项目的知识图谱"""
    url = PROJECTS[project_id]
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{url}/query",
            json={"query": question, "mode": mode}
        )
        return response.json()
```

### 健康检查

```bash
# 检查所有项目实例
for port in 3011 3012 3013; do
    echo -n "Port $port: "
    curl -s http://localhost:$port/health | jq -r '.status // "FAILED"'
done
```

---

## 方案二：动态 Workspace 路由（规划中）

> **状态**: 待开发，预计在 LoomGraph 集成稳定后实现

### 设计目标

单个 LightRAG 服务支持多 workspace 动态路由：

```
POST /api/v1/projects/{project_id}/insert_custom_kg
POST /api/v1/projects/{project_id}/query
GET  /api/v1/projects/{project_id}/health
```

### 技术方案

#### 核心改动

1. **Workspace 实例管理器**

```python
# lightrag/api/workspace_manager.py

class WorkspaceManager:
    """管理多个 workspace 的 LightRAG 实例"""

    def __init__(self, base_config: dict):
        self._instances: dict[str, LightRAG] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._base_config = base_config

    async def get_instance(self, workspace: str) -> LightRAG:
        """获取或创建 workspace 对应的 LightRAG 实例（懒加载）"""
        if workspace not in self._instances:
            async with self._get_lock(workspace):
                if workspace not in self._instances:
                    rag = LightRAG(
                        workspace=workspace,
                        **self._base_config
                    )
                    await rag.initialize_storages()
                    self._instances[workspace] = rag
        return self._instances[workspace]

    async def close_all(self):
        """关闭所有实例"""
        for rag in self._instances.values():
            await rag.finalize_storages()
```

2. **路由扩展**

```python
# lightrag/api/routers/project_routes.py

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

@router.post("/{project_id}/insert_custom_kg")
async def insert_custom_kg(
    project_id: str,
    request: InsertCustomKGRequest,
    manager: WorkspaceManager = Depends(get_workspace_manager)
):
    rag = await manager.get_instance(project_id)
    await rag.ainsert_custom_kg(request.custom_kg)
    return {"status": "success", "workspace": project_id}

@router.post("/{project_id}/query")
async def query(
    project_id: str,
    request: QueryRequest,
    manager: WorkspaceManager = Depends(get_workspace_manager)
):
    rag = await manager.get_instance(project_id)
    result = await rag.aquery(request.query, param=request.to_query_params())
    return result
```

3. **Header 方式（备选）**

利用已有的 `LIGHTRAG-WORKSPACE` header:

```python
@router.post("/query")
async def query(
    request: QueryRequest,
    workspace: str = Header(None, alias="LIGHTRAG-WORKSPACE"),
    manager: WorkspaceManager = Depends(get_workspace_manager)
):
    if not workspace:
        raise HTTPException(400, "LIGHTRAG-WORKSPACE header required")
    rag = await manager.get_instance(workspace)
    # ...
```

### 优点

- 单服务管理所有项目
- 共享 LLM/Embedding 连接
- 按需加载，节省资源
- API 更清晰

### 待解决问题

1. **实例生命周期管理**
   - LRU 淘汰长时间不用的实例
   - 内存上限控制

2. **并发安全**
   - 实例创建的锁机制
   - 跨 worker 的状态同步（如用 gunicorn 多进程）

3. **存储后端选择**
   - 文件存储: 适合少量项目
   - PostgreSQL: 推荐生产环境，原生支持 workspace 隔离

### 实现计划

| 阶段 | 任务 | 优先级 |
|------|------|--------|
| Phase 1 | WorkspaceManager 基础实现 | P1 |
| Phase 2 | `/api/v1/projects/` 路由 | P1 |
| Phase 3 | Header 方式支持 | P2 |
| Phase 4 | LRU 淘汰策略 | P2 |
| Phase 5 | PostgreSQL 后端验证 | P3 |

---

## 存储后端对比

| 后端 | Workspace 隔离方式 | 适用场景 |
|------|---------------------|----------|
| JsonKVStorage | 子目录 | 开发/小规模 |
| NetworkXStorage | 子目录 | 开发/小规模 |
| NanoVectorDBStorage | 子目录 | 开发/小规模 |
| PostgreSQL | `workspace` 字段 | 生产环境 |
| Redis | key 前缀 | 生产环境 |
| Neo4j | label 前缀 | 生产环境 |
| Milvus | collection 前缀 | 生产环境 |

---

## 推荐配置

### 开发环境（< 5 个项目）
- 方案一：多实例部署
- 文件存储后端
- 按需启动

### 生产环境（> 5 个项目）
- 方案二：动态 Workspace 路由
- PostgreSQL 后端
- 单服务 + 多 worker

---

## 相关文档

- [H200 部署指南](./H200_DEPLOYMENT.md)
- [LoomGraph 集成 API](../api/LOOMGRAPH_INTEGRATION.md)
