# H200 服务器部署指南

本文档记录 LightRAG 在 H200 GPU 服务器上的部署过程和配置要点。

## 服务架构

```
外部访问 (端口 3000-3499)
       │
       ├── :3000  GLM-4.7-fp8 (New API → SGLang)
       ├── :3001  LightRAG API (Nginx → :9621)
       └── :3002  TEI Embedding (Nginx → :9624)

内部服务
       │
       ├── :9621  LightRAG Server
       ├── :9624  TEI (Jina Code V2, GPU 4)
       └── :3000  New API → SGLang
```

## 前置条件

- NVIDIA H200 GPU (Hopper 架构, compute cap 9.0)
- Docker + NVIDIA Container Toolkit
- Nginx
- Python 3.12 + uv

## 部署步骤

### 1. TEI Embedding 服务

H200 使用 Hopper 专用镜像，普通 GPU 镜像会报 compute capability 不匹配错误。

```bash
# 下载模型
model=jinaai/jina-embeddings-v2-base-code
hf download $model

# 启动 TEI (注意使用 hopper 镜像)
docker run -d --name tei-jina \
  --gpus '"device=4"' \
  -p 9624:80 \
  -v /root/.cache/huggingface/hub/models--jinaai--jina-embeddings-v2-base-code:/model-repo \
  ghcr.io/huggingface/text-embeddings-inference:hopper-1.8 \
  --model-id /model-repo/snapshots/<snapshot-id> \
  --pooling mean

# 验证
curl http://localhost:9624/health
```

**关键点:**
- 必须使用 `ghcr.io/huggingface/text-embeddings-inference:hopper-1.8` 镜像
- 挂载整个 model repo 目录（包含 blobs/），不能只挂载 snapshot 目录（符号链接会失效）
- Jina v2 不需要 `--trust-remote-code`，v3 才需要
- 使用 `--pooling mean` 避免下载额外的 sentence_transformers 配置

### 2. LightRAG 服务

```bash
# 克隆代码
cd ~
git clone --branch loomgraph-main https://github.com/dreamlx/LightRAG.git lightrag
cd lightrag

# 安装依赖
uv sync --extra api

# 创建配置
cp env.example .env
mkdir -p data/rag_storage data/inputs
touch config.ini
```

编辑 `.env` 关键配置:

```bash
# LLM - GLM-4.7-fp8 via New API
LLM_BINDING=openai
LLM_MODEL=glm-4.7-fp8
LLM_BINDING_HOST=http://localhost:3000/v1
LLM_BINDING_API_KEY=<your-api-key>

# 禁用 GLM-4.7 的 thinking 模式
OPENAI_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
OPENAI_LLM_MAX_TOKENS=9000

# Embedding - Jina Code V2 via TEI
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=jinaai/jina-embeddings-v2-base-code
EMBEDDING_DIM=768
EMBEDDING_SEND_DIM=false
EMBEDDING_TOKEN_LIMIT=8192
EMBEDDING_BINDING_HOST=http://localhost:9624/v1
EMBEDDING_BINDING_API_KEY=dummy
```

启动服务:

```bash
source .venv/bin/activate
nohup python -m lightrag.api.lightrag_server > lightrag.log 2>&1 &

# 验证
curl http://localhost:9621/health
```

### 3. Nginx 反向代理

由于只有 3000-3499 端口对外开放，使用 Nginx 反向代理内部服务。

创建 `/etc/nginx/sites-available/lightrag`:

```nginx
# LightRAG API - port 3001
server {
    listen 3001;
    server_name _;

    client_max_body_size 200M;
    proxy_read_timeout 300s;
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:9621;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for streaming)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# TEI Embedding API - port 3002
server {
    listen 3002;
    server_name _;

    client_max_body_size 10M;
    proxy_read_timeout 60s;

    location / {
        proxy_pass http://127.0.0.1:9624;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

启用配置:

```bash
ln -sf /etc/nginx/sites-available/lightrag /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

## 外部访问端点

| 服务 | 端口 | URL | 用途 |
|------|------|-----|------|
| GLM-4.7-fp8 | 3000 | `http://<ip>:3000` | LLM 推理 |
| LightRAG | 3001 | `http://<ip>:3001` | 图 RAG API |
| TEI | 3002 | `http://<ip>:3002` | Embedding |

## LoomGraph 集成

LoomGraph 通过 HTTP API 访问 LightRAG:

```python
import httpx

LIGHTRAG_URL = "http://117.131.45.179:3001"

# 插入代码知识图谱 (跳过 LLM 提取)
async def insert_code_kg(custom_kg: dict):
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{LIGHTRAG_URL}/insert_custom_kg",
            json=custom_kg
        )
        return response.json()

# 查询
async def query(question: str, mode: str = "hybrid"):
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{LIGHTRAG_URL}/query",
            json={"query": question, "mode": mode}
        )
        return response.json()
```

### custom_kg 数据格式

```python
custom_kg = {
    "chunks": [
        {
            "content": "def login(username, password): ...",
            "source_id": "user_service.py:42",
            "file_path": "src/services/user_service.py"
        }
    ],
    "entities": [
        {
            "entity_name": "UserService.login",
            "entity_type": "method",
            "description": "用户登录验证方法",
            "source_id": "user_service.py:42"
        }
    ],
    "relationships": [
        {
            "src_id": "UserService.login",
            "tgt_id": "hashlib.sha256",
            "description": "调用 sha256 进行密码哈希",
            "keywords": "calls,dependency",
            "weight": 1.0
        }
    ]
}
```

## 常见问题

### TEI 启动失败: compute cap 不匹配

```
Error: Runtime compute cap 90 is not compatible with compile time compute cap 80
```

**原因**: H200 是 Hopper 架构 (compute cap 9.0)，默认 TEI 镜像为 Ampere (8.0) 编译。

**解决**: 使用 `ghcr.io/huggingface/text-embeddings-inference:hopper-1.8`

### TEI 启动失败: config.json not found

```
Error: `config.json` not found
```

**原因**: HuggingFace cache 使用符号链接，只挂载 snapshot 目录会导致链接失效。

**解决**: 挂载整个 model repo 目录:
```bash
-v /root/.cache/huggingface/hub/models--jinaai--jina-embeddings-v2-base-code:/model-repo
--model-id /model-repo/snapshots/<snapshot-id>
```

### GLM-4.7 返回空 content

**原因**: GLM-4.7 默认开启 thinking 模式，内容在 `reasoning_content` 字段。

**解决**: 在 `.env` 中禁用:
```bash
OPENAI_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
```

### LightRAG 端口被占用

```bash
# 查找占用进程
lsof -i :9621

# 停止旧进程
kill <pid>
```

## 服务管理

```bash
# 查看 TEI 日志
docker logs -f tei-jina

# 查看 LightRAG 日志
tail -f ~/lightrag/lightrag.log

# 重启 TEI
docker restart tei-jina

# 重启 LightRAG
pkill -f "lightrag.api.lightrag_server"
cd ~/lightrag && source .venv/bin/activate
nohup python -m lightrag.api.lightrag_server > lightrag.log 2>&1 &

# 重载 Nginx
systemctl reload nginx
```

## 健康检查

```bash
# TEI
curl http://localhost:9624/health

# LightRAG
curl http://localhost:9621/health

# 通过 Nginx
curl http://localhost:3001/health
curl http://localhost:3002/health
```
