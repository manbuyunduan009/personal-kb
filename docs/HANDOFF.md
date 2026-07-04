# 交付说明

这份说明用于把项目从当前电脑迁移到办公电脑。项目代码在 GitHub，模型权重、本地数据库、向量库数据和密钥不会跟随仓库提交。

## 1. 拉取代码

```powershell
git clone https://github.com/manbuyunduan009/personal-kb.git
cd personal-kb
```

## 2. 准备后端

办公电脑需要先安装 Python 3.9+。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

如果 `pip install -r requirements.txt` 因网络慢超时，可以分批安装：

```powershell
pip install fastapi uvicorn[standard] pydantic-settings openai python-docx openpyxl pytest
pip install fastembed
```

## 3. 配置后端

打开 `backend\.env`，按办公电脑实际路径修改：

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

说明：

- `DOCS_ROOT` 是要读取的本地资料目录，办公电脑路径可能不同。
- `EMBEDDING_PROVIDER=hash` 用来先跑通项目，不需要下载模型；改成 `fastembed` 才是真实本地开源 embedding。
- `HF_ENDPOINT` 用于模型下载。国内网络建议保留 `https://hf-mirror.com`。
- `OPENAI_API_KEY` 不填时，只能做语义检索，不能生成 AI 回答。
- `OPENAI_BASE_URL` 需要填写 OpenAI 兼容接口地址，通常要包含 `/v1`，例如 `https://example.com/v1`。
- `EMBEDDING_PROVIDER=fastembed` 时，第一次索引会下载开源 embedding 模型到本机缓存，不会下载到项目目录。

## 4. 启动后端

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

期望看到：

```text
ok: true
vector_ready: true
```

如果 `vector_ready` 是 `false`，先看 `vector_error`，通常是本地向量库初始化失败，或 `fastembed` 没装好。

## 5. 准备前端

办公电脑需要先安装 Node.js 20+。

```powershell
cd frontend
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

## 6. 首次验收步骤

1. 打开前端页面。
2. 确认顶部显示后端已连接。
3. 点击“索引文档”。
4. 等待文档列表出现 `.md`、`.docx`、`.xlsx`。
5. 输入问题，例如“专题验收助手的目标用户是谁？”
6. 先点“只检索”，确认右侧能命中文档片段。
7. 如果配置了 `OPENAI_API_KEY`，再点“AI 回答”，检查回答是否带引用来源。

也可以用固定问题集做命令行评测：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\eval_retrieval.py
```

期望看到 `Summary: 5/5 passed`。

## 7. 不会提交到 GitHub 的内容

这些内容是本地运行产物，不应该提交：

```text
backend/.venv/
backend/data/
frontend/node_modules/
frontend/dist/
.env
```

其中：

- `backend/data/` 里是 SQLite 元数据和本地向量库。
- `.env` 里可能有 API Key。
- embedding 模型权重通常在用户目录缓存，例如 Hugging Face cache。

## 8. 常见问题

### 页面显示“向量库未就绪”

进入后端虚拟环境后补装：

```powershell
pip install fastembed
```

### 点击索引很慢

第一次会下载 embedding 模型，并为每个文档切片生成向量。第一次慢是正常现象，之后未变化文件会跳过。

### 换电脑后文档列表为空

这是正常的。GitHub 不带本地向量库数据。换电脑后需要重新点击“索引文档”。

### AI 回答不可用

检查 `backend\.env`：

```text
OPENAI_API_KEY=你的 key
OPENAI_BASE_URL=你的 OpenAI 兼容接口地址
OPENAI_MODEL=你的模型名
```
