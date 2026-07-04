# 今晚开发目标：产品专家助手 v0.1

当前状态：P0 已落地，等待明天手动验收。

## 1. 今晚目标

今晚不做真实 embedding，不依赖办公电脑资料。

目标是把当前“个人知识库问答系统”推进到“产品专家助手”的第一层能力：

```text
从：问文档里写了什么
到：知道这些文档属于哪个需求、有哪些版本、版本之间改了什么
```

明天你可以验收的是：

- 工具里出现“产品专家”入口。
- 能看到系统识别出的需求分组。
- 能看到每个需求下有哪些文档版本。
- 能点击“查看卡片”，看到需求背景、目标、范围、规则、风险、验收点和待确认问题。
- 能点击“找相似”，看到相似历史需求、相似分和相似原因。
- 如果同一需求有两个版本，能做变更分析。
- 即使当前资料版本不足，也能看到清晰的提示和下一步工作方向。

## 2. 今晚 P0 范围

### P0-1 需求分组

状态：已完成。

系统根据文档标题、路径、内容预览推断：

- 项目名
- 需求名
- 需求 key
- 文档版本

第一版只做规则推断，不调用 AI。

验收标准：

- `专题验收助手PRD.md` 能被识别成一个需求。
- `《剑网3》十七周年庆线下活动小程序` 能被识别出项目和需求名。
- 前端能看到需求分组和文档数量。

### P0-2 版本列表

状态：已完成。

每个需求下展示关联文档：

- 文档标题
- 文件类型
- 更新时间
- 路径
- 是否为最新版本

验收标准：

- 前端“产品专家”区域能看到需求下的版本列表。
- 后端 API 能返回结构化 JSON。

### P0-3 变更分析 API

状态：已完成。

提供两个文档版本的对比能力：

- 新增内容
- 删除内容
- 字段修改
- 影响模块
- 需要确认的问题

第一版用规则 diff，不调用 AI。

验收标准：

- 两个文档 id 能提交到 API。
- API 返回变更摘要。
- 如果版本不足，前端显示明确原因。

### P0-4 前端入口

状态：已完成。

在当前工作台增加“产品专家”区域。

展示：

- 需求分组
- 最新文档
- 版本数量
- 变更分析入口
- 分析结果

验收标准：

- 页面不需要新路由，仍然是工作台。
- 能直接从当前页面看到产品专家能力。

### P0-5 需求卡片

状态：已完成。

基于需求最新文档，规则抽取：

- 需求背景
- 目标
- 用户/角色
- 范围/功能
- 关键规则
- 风险点
- 验收点
- 文档字段
- 待确认问题
- 下一步动作

验收标准：

- 产品专家面板里每个需求都有“查看卡片”按钮。
- 点击后能看到需求摘要、完整度评分、缺失章节、影响模块、待确认问题和下一步动作。
- 卡片不调用 AI，不依赖真实 embedding。

### P0-6 产品专家专项评测

状态：已完成。

新增脚本：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\eval_product_expert.py
```

评测内容：

- 需求分组数量。
- 版本数量。
- 单版本/多版本需求数量。
- 需求卡片生成成功率。
- 平均卡片完整度。
- 卡片质量分布。
- 最常缺失的章节。
- 相似需求生成成功率。
- 平均相似候选数量。
- 平均最高相似分。

验收标准：

- 后端启动后运行脚本，能输出 `Product Expert Eval`。
- `api_failure_count = 0`。
- `card_success_count` 大于 0。

### P0-7 相似历史需求

状态：已完成。

基于需求卡片做规则相似度检索：

- 需求卡片关键词重合。
- 影响模块重合。
- 同项目加权。
- 输出相似分、共同模块、共同关键词和相似原因。

验收标准：

- 产品专家面板里每个需求都有“找相似”按钮。
- 点击后能看到相似需求列表。
- 每条结果显示相似分和原因。
- 不调用 AI，不依赖真实 embedding。

## 3. 今晚 P1 范围

时间允许再做：

- 自动选择同一需求最新两个版本进行对比。
- 展示“下一步产品建议”。
- 给影响模块加分类标签，如页面、接口、权限、排期、运营配置。

## 4. 今晚不做

- 不切真实 embedding。
- 不下载模型。
- 不做 PDF/OCR。
- 不做复杂知识图谱。
- 不做登录和权限。
- 不做 LLM 方案推荐。
- 不做完整历史资料迁移。

## 5. 技术方案

### 后端新增能力

新增 `product_expert.py`：

- `infer_requirement_identity(document)`
- `group_documents_by_requirement(documents)`
- `build_requirement_card(requirement_key, documents)`
- `find_similar_requirements(requirement_key, documents, limit)`
- `build_requirement_timeline(requirement_key, documents)`
- `analyze_requirement_change(old_document, new_document)`

新增 API：

- `GET /api/product/requirements`
- `GET /api/product/requirements/{requirement_key}/card`
- `GET /api/product/requirements/{requirement_key}/similar`
- `GET /api/product/requirements/{requirement_key}/timeline`
- `POST /api/product/change-analysis`

新增脚本：

- `backend/scripts/eval_product_expert.py`

### 前端新增能力

新增类型：

- `RequirementGroup`
- `RequirementVersion`
- `RequirementCard`
- `SimilarRequirementsResult`
- `RequirementTimeline`
- `ChangeAnalysis`

新增 UI：

- 产品专家面板
- 需求分组列表
- 版本数量和最新文档
- 需求卡片按钮和卡片详情
- 卡片质量、完整度和缺失章节提示
- 相似需求按钮和相似结果列表
- 需求演进按钮和时间线结果列表
- 变更分析按钮
- 变更摘要展示

## 6. 明天验收方式

### 后端验收

```powershell
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe -m pytest
```

### 前端验收

```powershell
cd frontend
npm run build
```

### 手动验收

1. 启动后端和前端。
2. 点击“索引文档”。
3. 看右侧或中部是否出现“产品专家”区域。
4. 查看需求分组是否合理。
5. 点击“查看卡片”，确认能看到摘要、影响模块、待确认问题和下一步。
6. 点击“找相似”，确认能看到相似需求、相似分、共同模块或相似原因。
7. 点击“看演进”，确认能看到版本时间线、变更次数、风险等级和建议动作。
8. 如果某个需求只有一个版本，确认页面提示“当前只有一个版本，先补历史资料后才能看演进”。
9. 如果有两个版本，点击变更分析，确认能看到新增、删除、字段变化、影响模块。

### 产品专家评测

后端启动后运行：

```powershell
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe backend\scripts\eval_product_expert.py
```

预期：

- 输出 `Product Expert Eval`。
- `requirement_total` 大于 0。
- `card_success_count` 大于 0。
- `api_failure_count = 0`。

### 当前验证结果

- 后端测试：`72 passed`。
- 前端构建：`npm run build` 通过。
- 新增后端模块：`backend/app/product_expert.py`。
- 新增 API：
  - `GET /api/product/requirements`
  - `GET /api/product/requirements/{requirement_key}/card`
  - `GET /api/product/requirements/{requirement_key}/similar`
  - `GET /api/product/requirements/{requirement_key}/timeline`
  - `POST /api/product/change-analysis`
- 新增脚本：`backend/scripts/eval_product_expert.py`
- 新增前端入口：右侧“产品专家”面板。
- 临时后端 API 验证：`GET /api/product/requirements` 成功返回 4 个需求分组。
- 临时后端 API 验证：`GET /api/product/requirements/{requirement_key}/card` 成功返回需求卡片。
- 临时后端专项评测：`eval_product_expert.py` 通过，`card_success_count: 4/4`，`api_failure_count: 0`。
- 临时后端专项评测：相似需求通过，`similar_success_count: 4`，`avg_similar_count: 3.00`，`avg_top_similar_score: 0.42`。
- 临时后端专项评测：需求演进时间线通过，`timeline_success_count: 4`，`avg_timeline_versions: 1.00`，`avg_change_events: 0.00`，`avg_timeline_recommendations: 2.00`。

### P0-8 已完成：需求演进时间线 v1

做法：

1. 先按 `requirement_key` 找到同一需求的所有版本。
2. 把版本按 `last_modified + indexed_at` 从旧到新排序。
3. 对每个版本生成版本摘要：有效文本行数、结构字段数、影响模块。
4. 对相邻版本做 diff：新增、删除、字段变化、影响模块、风险等级。
5. 汇总反复变化的模块，给出建议动作。

为什么现在做：

- 你真正关心的是“这个需求历史上怎么变、现在该怎么做”。
- 如果没有时间线，AI 只能看到零散文档，很难判断历史演进。
- 先用规则版时间线打底，后续再接真实 embedding 和 LLM 方案推荐会更稳。

优点：

- 不依赖真实 embedding，今晚就能验收。
- 能把“最新两版对比”扩展成“整个需求历史演进”。
- 能发现反复变化的模块，帮助你判断高风险区域。

限制：

- v1 仍是文本 diff，不理解复杂 Word/Excel 版式。
- 版本归并依赖文件名、标题和字段抽取，后续需要人工修正入口。
- 当前只是产品判断入口，不替代最终人工确认。

## 7. 这一步的价值

这一步不是为了让 AI 立刻变聪明，而是给“产品专家能力”打地基。

底层逻辑：

- 问答靠 chunk。
- 变更分析靠 version。
- 历史方案复用靠 requirement。
- 产品建议靠 current requirement + historical similar requirements。

如果没有需求和版本结构，AI 只能随机翻文档；有了这层结构，它才可能回答：

- 这个需求历史上怎么变过？
- 当前版本和上一版差异是什么？
- 哪些模块会受影响？
- 历史上类似需求怎么做过？
- 现在最稳妥的方案是什么？

## 8. 明天之后的下一步

如果今晚 P0 做完，下一步做：

1. 需求卡片：自动生成背景、目标、用户、规则、风险、验收点。
2. 历史相似需求：基于需求卡片查相似项目。
3. 方案推荐：基于当前需求和历史相似需求给方案。
4. 产品交付清单：输出任务拆解、验收点、风险和同步对象。
