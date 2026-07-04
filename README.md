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
│  │  ├─ vector_store.py  # 本地 SQLite 向量库 + FTS/BM25 关键词库
│  │  ├─ query_rewrite.py # LLM 检索问题改写
│  │  ├─ product_expert.py # 需求分组、版本管理、需求卡片、相似需求、演进时间线
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
- [RAG 优化计划](docs/RAG_OPTIMIZATION_PLAN.md)：根据截图整理的 Small-to-Big、Chunk Header、Query Transformation、Rerank、反馈闭环等优化路线。
- [RAG 工业版 Playbook](docs/RAG_INDUSTRIAL_PLAYBOOK.md)：记录每批优化的顺序、原因、规则、测试结果和下一步。
- [产品专家路线图](docs/PRODUCT_EXPERT_ROADMAP.md)：把问答工具升级成历史需求、变更分析和方案建议助手的长期计划。
- [今晚开发目标](docs/NIGHTLY_DEVELOPMENT_TARGET.md)：明天验收用的产品专家 v0.1 目标和验收清单。

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
MIN_EVIDENCE_SCORE=0.30
```

如果没有配置 `OPENAI_API_KEY`，检索仍然可用；点击 AI 回答会返回明确的配置提示和引用来源。
如果检索结果最高分低于 `MIN_EVIDENCE_SCORE`，AI 回答会直接拒答，避免资料不足时硬编。

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
.\.venv\Scripts\python.exe -m pytest
```

测试覆盖：

- UTF-8 Markdown 解析
- Word 段落解析
- Excel sheet 和行内容解析
- 文本切片 overlap
- 重复索引时跳过未变化文件
- SQLite FTS/BM25 关键词索引
- LLM query rewrite 清洗和回退
- Citation Check 引用支撑检查
- Self-RAG 补救、trace 和评测报告

## 检索评测

后端启动并完成“索引文档”后，可以跑固定问题集：

```powershell
cd D:\vscode\动效\personal-kb\backend
.\.venv\Scripts\Activate.ps1
python scripts\eval_retrieval.py
```

脚本会检查固定检索问题是否命中预期文档，并检查问答是否带引用来源、无依据问题是否拒答。评测报告还会读取最近 trace，统计 LLM 改写率、召回方式、Citation Check 分布、引用支撑风险率和平均支撑分。

需要保存并对比评测报告时：

```powershell
python scripts\eval_report.py --save reports\baseline.json
python scripts\eval_report.py --compare reports\baseline.json --save reports\current.json
```

产品专家专项评测：

```powershell
python scripts\eval_product_expert.py
```

这个脚本会检查需求分组、需求卡片、相似需求和需求演进时间线是否能生成，并统计卡片完整度、缺失章节、待确认问题、下一步动作数量、相似需求数量、最高相似分、平均版本数和平均变更次数。

## 下一步练习

1. 给 `POST /api/index/run` 增加进度事件。
2. 给前端增加文档详情弹窗。
3. 增加 PDF 解析。
4. 把本地 SQLite 向量库换成 PostgreSQL + pgvector。
5. 增加登录，让每个用户有自己的知识库。
