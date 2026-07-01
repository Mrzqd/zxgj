# 装修管家

移动端优先的装修协作 Web 应用。后端 FastAPI，前端 React + Vite + TailwindCSS，数据使用 PostgreSQL，凭证和截图上传到 S3/S3-compatible 对象存储。

## 功能

- 用户注册、登录、JWT 鉴权
- 多人共管项目，项目拥有者可邀请已注册用户
- 装修记账：阶段、金额类别、子项、金额、付款凭证、备注
- 阶段事项：按装修阶段记录开工前和现场事项
- 物品比价：按空间/物品记录多个渠道报价和截图
- 验收清单：按阶段记录检查项、验收标准和状态
- 当前待办：截止时间、重要程度、完成状态
- AI 装修助手：内置装修知识库，支持上传 Markdown/TXT 文件，基于 RAG 检索回答

## 本地启动

1. 复制环境变量：

```bash
cp .env.example .env
```

2. 默认使用 Docker Compose 内置的 MinIO 作为 S3-compatible 对象存储，无需额外配置。

3. 启动：

```bash
docker compose up --build
```

4. 访问：

```text
前端：http://localhost:5173
后端：http://localhost:8000/docs
MinIO 控制台：http://localhost:9001
```

MinIO 默认账号密码均为 `minioadmin`，附件 bucket 为 `renovation-assets`。

## AI 知识库配置

AI 相关配置都在 `.env`，Docker Compose 会注入到后端容器。`MODELSCOPE_API_KEY` 可作为 embedding、rerank、LLM 的统一 token；如果分别配置 `EMBEDDING_API_KEY`、`RERANK_API_KEY`、`LLM_API_KEY`，则优先使用专用 key。

后端模型调用统一使用 OpenAI Python SDK 的兼容接口，即 `from openai import OpenAI`。当前默认使用 ModelScope 兼容 OpenAI 的推理接口：

```text
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
EMBEDDING_API_BASE=https://api-inference.modelscope.cn/v1
EMBEDDING_DIMENSIONS=4096
EMBEDDING_INDEX_DIMENSIONS=1536
```

向量存储使用 PostgreSQL + pgvector，Docker Compose 默认使用 `pgvector/pgvector:pg17`。Qwen3-Embedding-8B 原始 4096 维向量会保留用于精排；系统同时生成默认 1536 维本地投影向量，用于 pgvector `ivfflat` 索引召回。关键词与精确召回使用 PostgreSQL `pg_trgm` 索引。重排默认启用 ModelScope：

```text
RERANK_PROVIDER=openai_compatible
RERANK_MODEL=bge-reranker-v2.5-gemma2-lightweight
RERANK_API_BASE=https://api-inference.modelscope.cn/v1
```

知识库索引通过 Redis + RQ 后台任务执行。Docker Compose 会启动 `redis` 和 `knowledge-worker`；上传或更新知识库文件后会先显示 `pending/indexing` 状态，worker 完成后变为 `ready`，聊天请求不会同步向量化整份文档。

LLM 生成回答也在 `.env` 配置。默认 `LLM_PROVIDER=none`，系统会直接整理引用资料；要启用模型生成，配置兼容 `/chat/completions` 的模型：

```text
LLM_PROVIDER=openai_compatible
LLM_MODEL=你的生成模型
LLM_API_BASE=https://api-inference.modelscope.cn/v1
```

## 导入国家标准原文

标准原文不直接写进代码摘要里。后端提供 MinerU 导入脚本：把合法获取的 PDF/Word 标准文件放到 `backend/app/knowledge/raw/`，脚本会调用 MinerU 解析成 Markdown，写入 `backend/app/knowledge/documents/`，然后可立即向量化进知识库。

配置：

```text
MINERU_API_TOKEN=你的 MinerU API Token
MINERU_MODEL_VERSION=pipeline
```

导入单个标准：

```bash
cd backend
python -m app.scripts.import_standard_documents --ids GB-50327-2001 --index
```

Docker Compose 环境：

```bash
docker compose exec backend python -m app.scripts.import_standard_documents --ids GB-50327-2001 --index
```

标准清单在 `backend/app/knowledge/standards-manifest.json`。如果能拿到稳定官方下载地址，可填写 `source_url`；否则把文件放到对应 `local_path`。

## 开发命令

后端：

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```
