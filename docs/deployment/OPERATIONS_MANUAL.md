# LightRAG 运维手册

本文档记录 LightRAG 多租户部署的运维操作指南。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端调用链                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   codeindex (CLI)  →  LoomGraph (CLI)  →  LightRAG (API)       │
│      独立工具           调度编排            存储服务             │
│                                                                 │
│   耦合分析：                                                    │
│   ┌────────────┬────────┬──────────────────────────────────┐   │
│   │  集成方式  │ 耦合度 │               说明               │   │
│   ├────────────┼────────┼──────────────────────────────────┤   │
│   │ HTTP API   │ 松     │ 只依赖 REST 契约，可独立升级     │   │
│   ├────────────┼────────┼──────────────────────────────────┤   │
│   │ Python SDK │ 紧     │ 必须同环境安装，API 变化直接影响 │   │
│   └────────────┴────────┴──────────────────────────────────┘   │
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
│          └── :3020  智采云链 LightRAG                           │
│                     │                                           │
│                     ▼                                           │
│                  Nginx                                          │
│                     │                                           │
│          ┌─────────┴─────────┐                                 │
│          ▼                   ▼                                  │
│   :9610 LightRAG      :9620 LightRAG                           │
│   (pinpianyi)         (zhicaiyunlian)                          │
│          │                   │                                  │
│          └─────────┬─────────┘                                 │
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
| (共享) | TEI | 3002 | `http://117.131.45.179:3002` | Embedding 服务 |
| (共享) | LLM | 3000 | `http://117.131.45.179:3000` | GLM-4.7-fp8 |

### 内部服务

| 服务 | 内部端口 | 说明 |
|------|----------|------|
| pinpianyi_default | 9610 | 拼便宜 LightRAG |
| zhicaiyunlian_default | 9620 | 智采云链 LightRAG |
| TEI | 9624 | Jina Code V2 Embedding |
| PostgreSQL | 5432 | 数据库 (预留) |
| Redis | 6379 | 缓存 (预留) |

### 端口规划

```
3000       : GLM-4.7 LLM (New API) - 共享
3001       : 拼便宜 (旧端口, 向后兼容)
3002       : TEI Embedding - 共享
3010-3019  : 拼便宜 项目组
3020-3029  : 智采云链 项目组
3030-3039  : 预留 (新客户)
3040-3049  : 预留
...
```

## 目录结构

```
~/lightrag/                    # LightRAG 代码库
├── .venv/                     # Python 虚拟环境
└── lightrag/                  # 源码

~/lightrag-projects/           # 项目数据目录
├── pinpianyi_default/
│   ├── .env                   # 项目配置
│   ├── rag_storage/           # 图谱数据
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
LLM_BINDING_API_KEY=sk-KnZdHZmhMIjFFUHN1ZLybTZTDB62ZQQ4AA7RuYrtBiIH7arq
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
EOF
```

### 3. 添加 Nginx 配置

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

### 4. 启动服务

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

### Python 客户端示例

```python
import httpx
from typing import Optional

class LightRAGClient:
    """LightRAG HTTP API 客户端"""

    def __init__(self, base_url: str, timeout: float = 300):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    async def health(self) -> dict:
        """健康检查"""
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()

    async def insert_custom_kg(self, custom_kg: dict) -> dict:
        """插入代码知识图谱"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/insert_custom_kg",
                json={"custom_kg": custom_kg}
            )
            response.raise_for_status()
            return response.json()

    async def query(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: Optional[int] = None
    ) -> dict:
        """查询知识图谱"""
        payload = {"query": query, "mode": mode}
        if top_k:
            payload["top_k"] = top_k

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/query",
                json=payload
            )
            response.raise_for_status()
            return response.json()


# 使用示例
async def main():
    # 智采云链客户端
    client = LightRAGClient("http://117.131.45.179:3020")

    # 健康检查
    health = await client.health()
    print(f"Status: {health['status']}")

    # 插入代码图谱
    kg = {
        "chunks": [...],
        "entities": [...],
        "relationships": [...]
    }
    result = await client.insert_custom_kg(kg)

    # 查询
    answer = await client.query("如何实现用户认证？")
    print(answer["response"])
```

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

## 备份与恢复

### 备份数据

```bash
# 备份单个项目
tar -czf backup_pinpianyi_$(date +%Y%m%d).tar.gz \
  -C ~/lightrag-projects pinpianyi_default/

# 备份所有项目
tar -czf backup_all_$(date +%Y%m%d).tar.gz \
  -C ~/lightrag-projects .
```

### 恢复数据

```bash
# 停止服务
~/lightrag-projects/stop-instance.sh pinpianyi_default

# 恢复
tar -xzf backup_pinpianyi_20240208.tar.gz -C ~/lightrag-projects/

# 重启服务
~/lightrag-projects/start-instance.sh pinpianyi_default
```

## 监控建议

### 定期检查脚本

```bash
#!/bin/bash
# /root/scripts/check_lightrag.sh

# 检查所有实例
for dir in ~/lightrag-projects/*/; do
    project=$(basename "$dir")
    if [ -f "$dir/.env" ]; then
        source "$dir/.env"
        if ! curl -s --max-time 5 http://localhost:$PORT/health > /dev/null; then
            echo "ALERT: $project on port $PORT is DOWN"
            # 可以添加告警通知
        fi
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
