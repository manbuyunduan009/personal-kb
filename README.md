# Personal KB

一个教学型本地个人知识库 RAG 项目。第一版读取 `D:\vscode\动效\docs`，解析 `.md`、`.docx`、`.xlsx`，切片后写入本地 SQLite 向量库，并通过 OpenAI 兼容接口完成问答引用。

## 你正在学什么

1. 后端负责读取文件、解析文本、切片、入库、检索和调用大模型。
2. 前端负责提供一个工作台，让你触发索引、查看文档、搜索资料、发起问答。
3. RAG 的关键不是“直接问 AI”，而是先从你的资料里找证据，再让 AI 基于证据回答。

## 项目结构

```text
personal-kb
├─ backend
│  ├─ app
│  │  ├─ main.py          # FastAPI API 入口
│  │  ├─ parsers.py       # md/docx/xlsx 解析
│  │  ├─ chunking.py      # 文本切片
│  │  ├─ indexer.py       # 扫描 docs 并入库
│  │  ├─ vector_store.py  # 本地 SQLite 向量库
│  │  └─ rag.py           # 检索 + AI 问答
│  └─ tests
└─ frontend
   └─ src
      ├─ api.ts
      ├─ main.tsx
      └─ styles.css
```

## 重要文档

- [交付说明](docs/HANDOFF.md)：换电脑、部署到办公电脑、首次验收、常见问题。
- [RAG 质量说明](docs/RAG_QUALITY.md)：为什么 RAG 容易效果不好，以及本项目的质量路线。

## 后端启动

```powershell
cd D:\vscode\动效\personal-kb\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

默认使用 `EMBEDDING_PROVIDER=hash`，用于先跑通项目，不需要下载模型。它是词面匹配型向量，不等同于真实语义 embedding。

切到真实本地开源 embedding 时，把 `.env` 改成：

```text
EMBEDDING_PROVIDER=fastembed
```

第一次使用 `fastembed` 索引时会下载 `BAAI/bge-small-zh-v1.5`。这一步需要联网，耗时取决于网络和机器性能。

如果 `pip install -r requirements.txt` 因网络慢超时，直接重复执行同一条命令即可。也可以分批安装：

```powershell
pip install fastapi uvicorn[standard] pydantic-settings openai python-docx openpyxl pytest
pip install fastembed
```

## 前端启动

```powershell
cd D:\vscode\动效\personal-kb\frontend
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

## 环境变量

后端 `.env` 支持：

```text
DOCS_ROOT=D:\vscode\动效\docs
APP_DATA_DIR=./data
EMBEDDING_PROVIDER=hash
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
HF_ENDPOINT=https://hf-mirror.com
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

如果没有配置 `OPENAI_API_KEY`，检索仍然可用；点击 AI 回答会返回明确的配置提示和引用来源。

## API 快速检查

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/index/run
Invoke-RestMethod http://127.0.0.1:8000/api/documents
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/search -ContentType "application/json" -Body '{"query":"专题验收助手","limit":5}'
```

## 测试

```powershell
cd D:\vscode\动效\personal-kb\backend
pytest
```

测试覆盖：

- UTF-8 Markdown 解析
- Word 段落解析
- Excel sheet 和行内容解析
- 文本切片 overlap
- 重复索引时跳过未变化文件

## 检索评测

后端启动并完成“索引文档”后，可以跑固定问题集：

```powershell
cd D:\vscode\动效\personal-kb\backend
.\.venv\Scripts\Activate.ps1
python scripts\eval_retrieval.py
```

脚本会检查 5 个问题是否命中预期文档。现在默认 `hash` 模式用于验证链路；后面切到 `fastembed` 后，也用同一个脚本判断检索有没有变好。

## 下一步练习

1. 给 `POST /api/index/run` 增加进度事件。
2. 给前端增加文档详情弹窗。
3. 增加 PDF 解析。
4. 把本地 SQLite 向量库换成 PostgreSQL + pgvector。
5. 增加登录，让每个用户有自己的知识库。
