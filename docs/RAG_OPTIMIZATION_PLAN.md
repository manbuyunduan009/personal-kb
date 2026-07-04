# RAG 优化需求文档

## 1. 背景

当前项目已经跑通了个人知识库 RAG 主链路：文档解析、切片、向量化、检索、AI 回答和引用来源。下一阶段的目标不是继续堆功能，而是围绕“找得准、答得稳、可持续评测”优化 RAG 质量。

工业版开发顺序、每个模块的取舍原因、底层逻辑和学习记录统一沉淀在 [`RAG_INDUSTRIAL_PLAYBOOK.md`](./RAG_INDUSTRIAL_PLAYBOOK.md)。本文件偏需求和模块状态，Playbook 偏开发过程和学习路线。

截图里的优化方案可以理解为三类：

- 入库前优化：让每个切片带着更清楚的上下文进入向量库。
- 检索时优化：让用户随口问也能找到更可靠的片段。
- 回答后优化：让系统根据反馈和自检持续变好。

## 2. 优化方向提取

| 编号 | 方向 | 大白话解释 | 当前阶段做法 |
| --- | --- | --- | --- |
| 03 | Small-to-Big Retrieval | 用小块精准命中，再把更完整的大块交给 AI 作答。 | 已做 v1：每 3 个 child chunk 组成一个 parent context，检索仍命中 child，回答时补 parent。 |
| 04 | Context Enriched | 检索到一个片段时，补上标题、章节、前后文，让 AI 不只看到孤立句子。 | 给 chunk 存 `chunk_header`、上文、下文。 |
| 05 | Chunk Header | 入库前给每个切片加标题或章节主旨，提高检索匹配率。 | 从 Markdown 标题、章节行、文件名中推断块级标题。 |
| 06 | Document Augmentation | 为原文块补充高频潜在问题，让“问题匹配问题”更容易命中。 | 先用规则生成潜在问题，不额外调用模型。 |
| 07 | Query Transformation | 把用户模糊问题改写、泛化或拆成多个检索问题。 | 已做 v1：常规检索用规则 variant；Self-RAG 低分补救时可调用 LLM Query Rewrite。 |
| 08 | Rerank | 初筛多条结果，再用更细的规则或模型重排，选最可靠的 top 结果。 | 已做 v1：向量分、关键词分、BM25 小加分、标题分、反馈分共同排序。 |
| 09 | Sentence Window Retrieval | 命中核心句后自动向前后扩展，适合长文档和强上下文资料。 | 使用相邻 chunk 的前后窗口作为 prompt 上下文。 |
| 10 | Context Compression | 检索结果太长时，先压缩再喂给大模型，减少噪声和 token 浪费。 | 根据问题关键词挑选相关句子，限制每条上下文长度。 |
| 11 | Feedback Loop | 收集点赞、点踩、采用率，长期提升常用正确文档权重。 | 已做 v0：前端可反馈，后端存表，rerank 读取反馈分。 |
| 12 | Self-RAG | 回答前自检资料是否足够，剔除无用资料，不足时先补救，仍不足再拒答。 | 已做 v3：低分时先用 LLM/规则改写 query，再扩大召回补救；仍不足再拒答。 |
| 13 | RAG Trace | 记录每次问答的检索分数、补救状态、引用数量和耗时，让问题可以被诊断。 | 已做 v3：额外记录 Citation Check 状态、支撑分、检查 claim 数和原因。 |
| 14 | Eval Report | 把“这次优化有没有变好”变成数字，而不是靠感觉判断。 | 已做 v3：支持 Citation Check 分布、风险率和平均支撑分统计。 |
| 15 | Citation Check | 检查答案里的结论是否能被引用来源支撑，减少有引用但乱答。 | 已做 v1：接入 `/api/chat`、trace、前端诊断和评测报告；只记录风险，不拦截答案。 |
| 16 | SQLite FTS/BM25 | 用数据库全文检索补强专有名词、字段、编号等硬关键词召回。 | 已做 v1：`document_chunks_fts` + fallback keyword 表，和向量召回合并。 |

## 3. 模块状态和持续优化入口

这张表用于后续单独优化某个 RAG 模块。你每次只挑一行改，不要一口气把所有模块都动了。

| 模块 | 状态 | 已完成做法 | 关键文件 | 后续可优化点 |
| --- | --- | --- | --- | --- |
| 文档解析 | 已完成基础版 | 支持 `.md/.txt/.docx/.xlsx`，Word 读取段落和表格，Excel 读取 sheet 和行。 | `backend/app/parsers.py` | 增加 PDF、OCR、保留表格结构、识别标题层级。 |
| Chunk Header | 已完成 v0 | 入库时从 Markdown 标题、章节行、文件名推断 `chunk_header`。 | `backend/app/chunking.py` | 改成按标题分段；对 Word/Excel 识别更准确的章节标题。 |
| Document Augmentation | 已完成 v0 | 为每个 chunk 规则生成潜在问题，放进 embedding 文本，不伪装成原文展示。 | `backend/app/chunking.py`, `backend/app/indexer.py` | 用小模型生成更自然的问题；按业务类型生成不同问题模板。 |
| Context Enriched | 已完成 v1 | chunk 元数据保存标题、上文窗口、下文窗口、摘要；回答时优先使用 parent context。 | `backend/app/chunking.py`, `backend/app/vector_store.py`, `backend/app/rag.py` | 按标题/语义构造 parent，而不是固定 3 个 child 一组。 |
| Parent-Child Chunk | 已完成 v1 | 每 3 个 child chunk 生成一个 parent context；索引和引用仍落在 child；AI 回答上下文优先使用 parent。 | `backend/app/chunking.py`, `backend/app/indexer.py`, `backend/app/vector_store.py`, `backend/app/rag.py` | 按章节、标题、表格边界构造 parent；根据问题类型动态控制 parent 长度。 |
| Field-aware Retrieval | 已完成 v1 | 从文档表格/键值行提取文档级属性，把“项目/所属/负责人/日期/域名/编号”等字段传播到每个 chunk，并参与 embedding、关键词召回、rerank 和 prompt。 | `backend/app/chunking.py`, `backend/app/indexer.py`, `backend/app/retrieval.py`, `backend/app/rag.py` | 保留原始表格结构；给字段类型加权；把字段抽取规则配置化；支持更多业务字段。 |
| Query Transformation | 已完成 v1 | 常规检索用规则 query variant；Self-RAG 低分补救时调用 `query_rewrite.py` 做 LLM 改写，失败时回退规则。 | `backend/app/retrieval.py`, `backend/app/query_rewrite.py`, `backend/app/rag.py` | 支持子问题拆解；为多轮追问注入对话上下文；按问题类型决定是否调用 LLM。 |
| SQLite FTS/BM25 | 已完成 v1 | 入库时同步写 `document_chunks_keyword` 和 `document_chunks_fts`；检索时调用 `keyword_search`，FTS5 可用时使用 BM25，不可用时降级关键词扫描。 | `backend/app/vector_store.py`, `backend/app/rag.py` | 给标题/字段/正文设置不同权重；支持精确短语；进一步优化中文分词。 |
| Hybrid Search | 已完成 v1 | 向量召回、BM25/关键词召回并行，合并候选后 rerank；前端展示召回方式、BM25 分和命中关键词。 | `backend/app/vector_store.py`, `backend/app/retrieval.py`, `backend/app/rag.py`, `frontend/src/main.tsx` | 按问题类型调权重；把 topK 候选明细写进 trace。 |
| Rerank | 已完成 v1 | 用向量分、关键词重合度、标题重合度、BM25 小加分、反馈分做轻量重排。 | `backend/app/retrieval.py` | 接 cross-encoder rerank 模型；按不同文档类型定制权重。 |
| Sentence Window Retrieval | 已完成 v0 | 回答时把命中 chunk 的前后窗口一起放进上下文。 | `backend/app/rag.py` | 根据命中句定位更精确的句子窗口；长文档按段落窗口扩展。 |
| Context Compression | 已完成 v0 | 超长上下文按问题关键词挑相关句子，并限制长度。 | `backend/app/retrieval.py`, `backend/app/rag.py` | 用 LLM 压缩；保留表格行标题；按引用来源分别压缩。 |
| Feedback Loop | 已完成 v0 | 前端对引用/检索结果点赞点踩；后端存 `feedback` 表；rerank 用反馈分小幅加权。 | `backend/app/db.py`, `backend/app/main.py`, `backend/app/retrieval.py`, `frontend/src/main.tsx` | 加反馈备注；按问题相似度加权；做“已反馈”状态；加入评测报表。 |
| Self-RAG | 已完成 v3 | Prompt 要求判断资料是否支持问题；回答前过滤低分 chunk；首次证据不足时使用 LLM/规则 query rewrite，扩大召回再检索；补救后仍不足才拒答。 | `backend/app/rag.py`, `backend/app/query_rewrite.py`, `backend/app/config.py`, `backend/scripts/eval_retrieval.py`, `frontend/src/main.tsx` | 增加按问题类型的阈值；让模型做引用一致性检查；记录补救成功案例。 |
| RAG Trace | 已完成 v3 | 每次 `/api/chat` 写入诊断记录；额外记录改写来源、召回方式、Citation Check 状态、支撑分、检查 claim 数和原因；前端展示这些诊断信息。 | `backend/app/db.py`, `backend/app/main.py`, `frontend/src/api.ts`, `frontend/src/main.tsx` | 增加 trace 详情页；记录 topK 候选列表；支持按问题搜索 trace。 |
| Eval Report | 已完成 v3 | 新增脚本跑固定问题集，支持 `--save` 保存 JSON、`--compare` 对比基线，并输出 trace 改写率、召回方式和 Citation Check 风险指标。 | `backend/scripts/eval_report.py`, `backend/tests/test_eval_report.py`, `backend/reports/.gitignore` | 做趋势图；保存多次评测快照；把风险样例导出成待优化问题集。 |
| Citation Check | 已完成 v1 | 新增独立规则模块，用答案 claim 和引用证据做词面支持度检查；已接入问答返回、trace、前端诊断和 eval report；当前只记录不拦截。 | `backend/app/citation_check.py`, `backend/app/rag.py`, `backend/app/db.py`, `frontend/src/main.tsx`, `backend/scripts/eval_report.py`, `backend/tests/test_citation_check.py` | 按 claim 输出具体对应引用；低支持度时支持人工复核；后续接 LLM judge 做二次判断。 |

## 4. 已完成模块的实现说明

### 4.1 Chunk Header

做法：

1. `split_text` 仍然负责基础切片。
2. `build_chunk_records` 在切片后为每块生成结构化信息。
3. `infer_chunk_header` 优先找 Markdown 标题、章节编号、短标题行；找不到时回退到文件名。

为什么这样做：

- 原始 chunk 只有正文，检索时容易缺上下文。
- 标题进入 embedding 文本后，用户问“某某需求/目标/阶段”更容易命中对应块。

后续你可以单独优化：

- 把固定字符切片改成“先按标题切，再控制长度”。
- 给 `.docx` 解析结果增加标题样式识别。

### 4.2 Document Augmentation

做法：

1. `generate_potential_questions` 根据关键词生成“有哪些需求、目标是什么、目标用户是谁”等潜在问题。
2. `indexer` 用“文档名 + 章节 + 潜在问题 + 正文”生成 embedding。
3. 前端和引用仍然展示原始正文，避免把生成问题当成原文证据。

为什么这样做：

- 用户提问和文档原文不一定用同一套词。
- 让“问题匹配问题”可以补足纯正文检索的盲区。

后续你可以单独优化：

- 为 PRD、进度表、需求文档分别设计问题模板。
- 后续接本地小模型或在线模型批量生成更高质量潜在问题。

### 4.3 Query Transformation

做法：

1. `query_variants` 保留原问题。
2. 根据“需求、目标用户、阶段、验收、活动”等关键词扩展 query。
3. 对复合问题做简单拆分，多路检索后合并结果。

为什么这样做：

- 用户常常说得很口语，比如“这个小程序要做啥”。
- 多 query 召回能提高找到正确文档的概率。

后续你可以单独优化：

- 用 LLM 把口语问题改写成 3 到 5 个专业检索问题。
- 对“多个问题合在一起”的输入做子问题拆解。

### 4.4 Hybrid Search

做法：

1. 向量召回继续负责找“语义相近”的候选片段。
2. `keyword_recall_hits` 同时扫描所有 chunk，找“字面关键词命中”的候选片段。
3. 两路候选按 chunk id 合并，同一个片段会标记为 `hybrid`。
4. 前端显示召回方式：向量、关键词、混合。
5. rerank 时会把 `keyword_recall_score` 纳入最终分。

为什么这样做：

- 向量检索像“找意思相近的内容”，关键词检索像“查字典找原词”。
- 需求文档里有很多专有名词、日期、模块名、表格字段，精确词命中很重要。
- 如果第一步召回漏掉了正确片段，后面的 rerank 再聪明也排不到它。

后续你可以单独优化：

- 把当前轻量关键词扫描替换成 SQLite FTS 或 BM25。
- 对标题、文件名、生成问题、正文设置不同关键词权重。
- 支持引号包裹的精确短语搜索。

### 4.5 Rerank

做法：

当前公式在 `backend/app/retrieval.py`：

```text
最终分 = 向量分 * 0.56 + 关键词分 * 0.24 + 标题分 * 0.08 + 混合召回加分 + 反馈加分
```

反馈加分目前最多正负 `0.12`，避免用户误点一次就完全改变排序。

为什么这样做：

- 向量检索负责粗召回。
- 关键词和标题负责纠偏。
- 用户反馈负责长期微调。

后续你可以单独优化：

- 把权重抽成配置项。
- 接真实 rerank 模型。
- 按文档类型设置不同权重。

### 4.6 Feedback Loop

做法：

1. 前端在引用和检索结果里显示“有帮助 / 没帮助”按钮。
2. 后端 `POST /api/feedback` 记录反馈事件。
3. 后端 `GET /api/feedback/summary` 汇总每个 chunk 的正负反馈。
4. 检索和问答时读取反馈汇总，传给 rerank 作为小幅加权。

为什么这样做：

- RAG 不是一次调好，而是靠真实使用不断发现哪些片段可靠。
- 先做事件记录，后续才能做统计、报表和学习。

后续你可以单独优化：

- 前端显示某条引用是否已经反馈。
- 增加“为什么没帮助”的备注选项。
- 把反馈和相似问题关联，而不是全局加权。

### 4.7 Self-RAG

做法：

1. 系统 prompt 要求回答前判断资料是否直接支持问题。
2. `MIN_EVIDENCE_SCORE` 控制最低证据阈值，默认 `0.30`。
3. 问答前过滤低分 chunk，只把达标片段交给 AI。
4. 如果第一次没有达标片段，不马上拒答，而是生成补救 query，扩大召回范围再检索一次。
5. 如果二次检索找到达标证据，就继续交给 AI 回答；如果仍然不足，才回答“文档中没有找到依据”。
6. API 返回 `self_rag` 状态，包括是否触发补救、补救 query、初始最高分、最终最高分、证据阈值。
7. 前端展示 Self-RAG 检查状态，方便判断问题是“第一次就找到”还是“二次补救后找到”。
8. 评测脚本增加 `CHAT` 检查：正常问题必须带引用，无依据问题必须拒答。

为什么这样做：

- 检索分数太低时，AI 很容易把弱相关资料包装成看似合理的答案。
- 先用阈值做第一道门，可以减少“硬答”和幻觉；但直接拒答太粗暴，所以低分时先补救检索。
- 阈值是可调参数，后续要靠评测集慢慢校准。

当前边界：

- v2 的补救 query 还是规则生成，不额外调用 LLM 改写问题。
- v2 是“检索补救”，还不是完整 Self-RAG 论文里的多步自问、自评、过滤闭环。
- 下一版可以让在线模型生成更自然的 query rewrite，再让模型判断“引用是否真的支撑答案”。

后续你可以单独优化：

- 将 `MIN_EVIDENCE_SCORE` 按不同 embedding 模型单独配置。
- 对“关键词强命中”和“语义强命中”设置不同阈值。
- 让模型生成 query rewrite，并输出“证据是否足够”的内部判断，再生成最终回答。
- 对生成结果做引用一致性检查。

### 4.8 Field-aware Retrieval

做法：

1. 入库时先从整篇解析文本里提取文档级字段，例如项目/部门所属、负责人、对接人、日期、域名、编号等。
2. 每个 chunk 仍然保留自己的正文，但额外带上 `document_facts`、`chunk_facts` 和合并后的 `field_facts`。
3. 生成 embedding 时，把文档属性和正文一起放进去；检索、关键词召回、rerank 和 AI prompt 也都能看到这些字段。
4. Self-RAG 只在“用户问题像是在问字段属性”时，才允许字段证据补充分数；普通内容问题仍然要看正常检索分。

为什么这样做：

- 很多 PRD 和需求文档会把“这是谁的项目、属于哪个产品、谁负责、什么时候完成”写在表格里，把具体需求写在正文里。
- 普通切片会把表格字段和正文拆开，导致系统找到正文但不知道它属于哪个项目，或者找到字段但不知道它对应哪段业务内容。
- 字段和正文绑定后，系统不是记住某个特例，而是学会“文档基础信息属于整篇文档，可以作为每个片段的上下文”。

边界和约束：

- 不写“周年庆=剑网3”这种项目特例。
- 只有字段类问题才使用字段证据，例如“属于哪个项目、哪个游戏、负责人是谁、什么时候完成、域名是什么”。
- 字段证据不能无条件绕过阈值，仍然需要有一定检索相关度，避免把完全无关文档拿来硬答。

后续你可以单独优化：

- 保留 Word/Excel 表格的行列结构，而不是只转成纯文本。
- 给字段做类型识别，例如“归属字段、人员字段、时间字段、链接字段、编号字段”。
- 用 SQLite FTS 或 BM25 对字段、标题、正文设置不同权重。
- 把字段抽取规则做成配置文件，方便你以后按公司文档模板扩展。

### 4.9 检索问题处理原则

以后遇到检索问题，需求文档里统一按这个格式记录，不写特殊情况补丁：

1. 现象：用户问了什么，系统返回了什么。
2. 根因：链路上哪一步出了问题，是解析、切片、字段关系、召回、rerank、Self-RAG 阈值，还是 prompt。
3. 通用能力缺口：这个问题背后缺的是哪类能力。
4. 解决方案：补通用能力，不写某个项目、某个文件、某个问题的硬编码规则。
5. 验证用例：把失败问题加入评测脚本，防止以后改坏。

本次问题记录：

- 现象：用户问“周年庆是哪个游戏的？”，检索结果能命中文档，但 AI 回答阶段因为最高分低于 Self-RAG 阈值而拒答。
- 根因：问题问的是文档级字段“项目/部门所属”，这个字段在需求基础信息表格里；正文 chunk 讲的是周年庆小程序需求。旧链路没有稳定表达“表格字段属于整篇文档，应该成为正文 chunk 的上下文”。
- 通用能力缺口：字段和正文没有建立关系，导致字段类问题只能靠文本相似度碰运气。
- 解决方案：做 Field-aware Retrieval，把文档级字段提取出来传播到每个 chunk，并让字段类问题可以使用字段证据参与 Self-RAG 判断。
- 验证用例：加入“周年庆是哪个游戏的？”评测，要求命中并引用 `【需求管理】《剑网3》十七周年庆线下活动小程序.docx`。

### 4.10 RAG Trace 观测系统

做法：

1. 后端新增 `rag_traces` 表，记录每次问答运行的诊断信息。
2. `/api/chat` 在生成答案后写入 trace，并把 `trace_id` 返回给前端。
3. 新增 `GET /api/traces`，用于查看最近的问答诊断记录。
4. 前端右侧新增“RAG 诊断”面板，展示最近问题、Self-RAG 状态、初始最高分、最终最高分、是否补救、引用数量和耗时。

为什么这样做：

- 工业版 RAG 的第一件事不是换更大的模型，而是先看清楚链路。
- 只看最终答案很容易误判：回答错可能是解析错、切片错、召回漏、排序错、阈值过高，也可能是生成阶段幻觉。
- Trace 相当于 RAG 的运行日志。每一次问题都留下证据，后续优化 BM25、Parent Chunk、Query Rewrite、Rerank 时才能比较前后效果。

底层逻辑：

- `initial_best_score` 看第一次检索质量。
- `final_best_score` 看补救后是否变好。
- `rescue_attempted` 和 `rescued` 看 Self-RAG 补救是否真的有用。
- `citation_count` 和 `cited_titles` 看答案是否有来源支撑。
- `is_refusal` 看系统是不是因为证据不足而拒答。
- `latency_ms` 看优化是否带来了明显耗时。

后续你可以单独优化：

- 记录 topK 候选片段和每个候选的分数拆解。
- 给 trace 做筛选：只看拒答、只看补救成功、只看无引用回答。
- 生成评测报表：平均分、拒答率、补救率、平均耗时。
- 把 trace 和用户反馈关联起来，分析“用户点踩的回答当时检索链路哪里出问题”。

### 4.11 Parent-Child Chunk

做法：

1. 入库时仍然先切成 800 字左右的 child chunk，保证检索颗粒度足够细。
2. 每 3 个连续 child chunk 组合成一个 parent context，最多保留 2600 字。
3. 每个 child metadata 里保存 `parent_index` 和 `parent_context`。
4. 检索、引用、反馈仍然指向具体 child chunk。
5. AI 回答时优先使用 parent context，送给模型的上下文再压缩到约 1200 字。
6. 索引版本升级为 `small-to-big-parent-child-v1`，所以需要重新点击“索引文档”或调用 `/api/index/run`。

为什么这样做：

- 小块适合“找”：问题通常只对应文档里一小段，child 越精准越容易命中。
- 大块适合“答”：AI 如果只看到一句孤立片段，很容易丢前因后果，parent 可以补上下文。
- 引用仍指向 child，是为了让用户知道答案到底从哪一小段来的。

当前边界：

- v1 是固定每 3 个 child 一组，不理解真实章节结构。
- parent context 会重复存到多个 child metadata，索引体积会变大。
- 上下文压缩仍是规则筛句，不是模型级压缩。

后续你可以单独优化：

- 按 Markdown 标题、Word 标题样式、Excel sheet/行块来构造 parent。
- 不重复存 parent，而是单独建 parent 表，通过 `parent_id` 关联 child。
- 按问题类型动态决定是用 child、parent，还是更大的 document window。

### 4.12 Eval Report

做法：

1. 复用 `eval_retrieval.py` 里的固定检索问题和问答问题。
2. 依次调用 `/api/search`、`/api/chat`、`/api/traces`。
3. 输出检索通过率、问答通过率、拒答率、补救率、平均耗时和最近 trace 状态分布。
4. 命令为：

```powershell
cd D:\vscode\动效\personal-kb\backend
.\.venv\Scripts\python.exe scripts\eval_report.py
```

为什么这样做：

- 工业版 RAG 不能只靠“我感觉这次更准了”。
- 每次改 chunk、rerank、query rewrite、阈值，都要用同一批问题复测。
- 报告指标能告诉你：是命中率变了，还是拒答率变了，还是耗时变高了。

当前指标口径：

- `search_pass_rate`：只检索时，期望文档是否出现在 top 结果里。
- `chat_pass_rate`：AI 问答时，期望引用是否出现，或无依据问题是否正确拒答。
- `refusal_rate`：成功问答里有多少次拒答。
- `rescue_rate`：触发补救的问题里，有多少被补救成功。
- `recent_trace_citation_check_risk_rate`：最近 trace 中，引用支撑偏弱或不足的比例。
- `recent_trace_avg_citation_support_score`：最近 trace 的平均引用支撑分。
- `avg_latency_ms`：搜索和问答的平均耗时。

后续你可以单独优化：

- 输出 JSON 文件，保存每次评测快照。
- 加趋势对比：本次 vs 上次。
- 把 Citation Check 的风险样例导出成待优化问题集。

### 4.13 Citation Check

做法：

1. 新增 `check_citation_support(answer, citations)` 独立函数。
2. 先把答案拆成可检查 claim。
3. 再从引用里收集标题、摘要、上下文、字段事实等证据文本。
4. 用中文 2/3 字 ngram、英文词、数字一致性做支持度评分。
5. 返回 `supported`、`warning`、`unsupported` 三类状态。
6. `/api/chat` 生成答案后调用 Citation Check，并把结果随答案返回。
7. `rag_traces` 保存 `citation_check_status`、`citation_support_score`、`citation_checked_claim_count`、`citation_check_reasons`。
8. 前端回答区和右侧 RAG 诊断显示引用检查状态。
9. `eval_report.py` 统计最近 trace 的 Citation Check 分布、风险率和平均支撑分。

为什么这样做：

- RAG 最危险的问题不是“没有引用”，而是“看起来有引用，但答案结论不是引用里说的”。
- v0 先做规则检查，成本低、可测试、可解释。
- v1 接入 Trace 但不拦截答案，先让系统看见风险，再决定后续是否阻断。

大白话理解：

- 引用来源像“证据袋”，答案像“结论”。
- Citation Check 做的事就是：把结论拆开，回证据袋里找有没有相同事实。
- 如果找得到，状态是 `supported`；只找到一部分是 `warning`；基本找不到是 `unsupported`。
- `not_applicable` 表示这次不是正常答案，比如证据不足拒答、没配置 API key、AI 调用失败，这类不应该被算成“引用不支撑”。

当前边界：

- 它是词面检查，不理解复杂推理、否定关系和多跳事实。
- 如果引用上下文不完整，检查会偏保守。
- 不应该把它当最终裁判，现阶段更适合作为 trace 风险信号。
- 当前不拦截答案，只记录风险，避免规则误伤正常回答。

后续你可以单独优化：

- 做 claim-by-claim 明细：每个结论对应哪条引用，哪条没有依据。
- 在 trace 详情页显示完整证据对比。
- 后续再用 LLM 做 claim-by-claim 检查，但要保留规则版作为低成本底线。

### 4.14 SQLite FTS/BM25

做法：

1. 入库时除了保存向量，还同步写入 `document_chunks_keyword`。
2. 如果本机 SQLite 支持 FTS5，再写入 `document_chunks_fts`。
3. 检索时先走 `keyword_search`，FTS5 可用时用 `bm25()` 排序，不可用时回退到普通关键词扫描。
4. BM25 命中的结果和向量召回结果按 chunk id 合并。
5. rerank 时给 BM25 命中一个小加分 `0.04`，让硬关键词有影响力，但不压过语义相关性。

为什么这样做：

- 向量检索适合“意思相近”，但对项目名、编号、字段名、域名、人名这类硬词不一定稳定。
- BM25 像搜索引擎，适合“文档里真的出现过这个词”的场景。
- 两者合并后，既能找语义，也能抓专有名词。

当前边界：

- 中文目前主要靠 2/3 字 ngram 辅助，不是真正中文分词。
- BM25 只能证明词出现过，不能证明答案一定正确。
- 旧索引库需要重新索引，才能把历史 chunk 写入关键词表。

后续你可以单独优化：

- 给标题、字段、正文设置不同 BM25 权重。
- 支持用户输入引号时做精确短语搜索。
- 把 topK 候选和分数拆解写进 trace，方便看 BM25 是如何影响排序的。

### 4.15 LLM Query Rewrite

做法：

1. 常规检索仍然使用规则 `query_variants`，不额外调用 AI。
2. 当 Self-RAG 判断首次检索证据不足时，调用 `rewrite_queries`。
3. 有 API key 时让在线模型生成更适合检索的 query；没有 key 或调用失败时回退规则 query。
4. 改写结果会清洗、去重、限长、限量，避免模型输出解释文本。
5. `self_rag` 和 trace 会记录是否使用 LLM、改写来源、改写错误和最终补救 query。

为什么这样做：

- 用户的问题可能太短、太口语、缺少业务词。
- LLM 改写不是回答问题，而是帮系统“换几种搜索问法”。
- 只在低分补救时调用，可以控制成本和延迟。

当前边界：

- LLM 有可能改偏，所以必须保留 fallback query。
- 当前还没有做复杂问题的子问题拆解和多轮上下文理解。
- 如果在线模型慢，低分问题的响应会变慢。

后续你可以单独优化：

- 让 LLM 输出结构化结果：明确化 query、关键词 query、子问题 query。
- 按问题类型决定是否启用 LLM 改写。
- 把 query rewrite 前后的命中变化纳入 Eval Report。

### 4.16 Eval Report 对比

做法：

1. `eval_report.py --save reports/latest.json` 保存完整评测结果。
2. `eval_report.py --compare reports/baseline.json` 和指定基线对比。
3. 对比指标包括命中率、问答通过率、拒答率、补救率、平均耗时和 API 失败数。
4. 报告还会统计最近 trace 的 LLM 改写率和召回方式分布。
5. `backend/reports/.gitignore` 会忽略真实报告 JSON，避免把本地评测数据提交到仓库。

为什么这样做：

- 工业版 RAG 优化必须看趋势，不能只看单次结果。
- BM25、Query Rewrite、阈值调整都可能一部分问题变好、一部分问题变差。
- 对比报告可以帮助你判断这次改动是整体提升，还是只解决了某个样例。

后续你可以单独优化：

- 保存多次评测快照，生成趋势表。
- 加 Citation Check 的 supported/warning/unsupported 比例。
- 把每道题的 topK 变化也写进报告。

## 5. 目标

1. 检索结果更容易命中正确文档和正确片段。
2. AI 回答时能看到更完整但不过载的上下文。
3. 每次优化都能通过固定评测脚本验证是否变好。
4. 保持教学项目的可读性，不一开始引入过多模型和服务。

## 6. 非目标

- 第一阶段不接真实 rerank 模型，避免安装和下载成本过高。
- 第一阶段不做 PDF、OCR、图片识别。
- 第一阶段不做多用户反馈系统。
- 第一阶段不把 SQLite 向量库替换成复杂向量数据库。

## 7. 分阶段计划

### 第一阶段：低依赖质量增强

这一阶段不额外下载新模型，主要改入库文本和检索排序。

- 给 chunk 增加块级标题。
- 给 chunk 增加潜在问题。
- 给 prompt 增加前后文窗口。
- 查询时生成多个改写 query。
- 检索后用轻量 rerank 重排。
- 对送入大模型的上下文做长度压缩。

验收标准：

- 原有 5 个检索评测问题继续通过。
- “十七周年庆小程序有哪些需求？”能命中小程序需求文档。
- 检索结果能看到更清楚的标题和片段来源。

### 第二阶段：可观测和反馈闭环

- 前端增加“有帮助 / 没帮助”反馈按钮。已完成 v0。
- 后端新增 feedback 表。已完成 v0。
- 搜索结果根据历史正反馈做小幅加权。已完成 v0。
- 评测脚本增加 answer/citation 检查。

验收标准：

- 用户可以对回答或引用反馈。
- 同一问题多次反馈后，正确文档排序更靠前。

### 第三阶段：模型级增强

- 接真实 rerank 模型。
- 尝试真实本地 embedding。
- 对复杂问题做 LLM query rewrite。
- 对长上下文做 LLM compression。

验收标准：

- 对比第一阶段评测结果，top 3 命中率提升。
- 答案引用更集中，废片段减少。

## 8. 教学重点

- RAG 不是一个功能，而是一条链路。
- 优化优先级通常是：文档质量 > 切片策略 > 检索策略 > 重排 > Prompt > 模型。
- 不要只看 AI 最终回答，要先看检索片段是否靠谱。
- 每次优化都要用固定问题集复测，否则很容易凭感觉误判。
- 每次新增工业版模块后，都要同步更新 [`RAG_INDUSTRIAL_PLAYBOOK.md`](./RAG_INDUSTRIAL_PLAYBOOK.md)，记录先后顺序、为什么、优劣、规则和验证方式。
- 使用子智能体并行开发时，每个子任务都必须交付代码、测试结果和 Playbook 记录；没有文档记录的模块不算真正交付。
