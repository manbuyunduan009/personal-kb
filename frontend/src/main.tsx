import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  BookOpen,
  Database,
  FileText,
  GitBranch,
  Lightbulb,
  Loader2,
  MessageSquareText,
  Play,
  Search,
  Server,
  Sparkles,
  Tags,
  ThumbsDown,
  ThumbsUp
} from "lucide-react";
import {
  analyzeChange,
  chat,
  ChangeAnalysis,
  Citation,
  CitationCheck,
  DocumentItem,
  DomainTermCandidate,
  DomainTermCandidatesResult,
  getDocuments,
  getDomainTermCandidates,
  getHealth,
  getProductRequirements,
  getRequirementCard,
  getRequirementTimeline,
  getSimilarRequirements,
  getSolutionRecommendation,
  getTraces,
  Health,
  IndexResult,
  RequirementCard,
  RagTrace,
  RequirementTimeline,
  RequirementGroup,
  runIndex,
  search,
  SearchHit,
  SelfRagStatus,
  SimilarRequirementsResult,
  SolutionRecommendation,
  submitFeedback
} from "./api";
import "./styles.css";

function formatDate(value: string) {
  return value ? new Date(value).toLocaleString("zh-CN") : "-";
}

function shortPath(path: string) {
  const parts = path.split(/[\\/]/);
  return parts.slice(Math.max(0, parts.length - 3)).join(" / ");
}

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [question, setQuestion] = useState("专题验收助手的目标用户是谁？");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [citationCheck, setCitationCheck] = useState<CitationCheck | null>(null);
  const [results, setResults] = useState<SearchHit[]>([]);
  const [traces, setTraces] = useState<RagTrace[]>([]);
  const [requirements, setRequirements] = useState<RequirementGroup[]>([]);
  const [termCandidates, setTermCandidates] = useState<DomainTermCandidatesResult | null>(null);
  const [requirementCard, setRequirementCard] = useState<RequirementCard | null>(null);
  const [similarRequirements, setSimilarRequirements] = useState<SimilarRequirementsResult | null>(null);
  const [requirementTimeline, setRequirementTimeline] = useState<RequirementTimeline | null>(null);
  const [solutionRecommendation, setSolutionRecommendation] = useState<SolutionRecommendation | null>(null);
  const [changeAnalysis, setChangeAnalysis] = useState<ChangeAnalysis | null>(null);
  const [indexResult, setIndexResult] = useState<IndexResult | null>(null);
  const [loading, setLoading] = useState<
    | "index"
    | "search"
    | "chat"
    | "product"
    | "card"
    | "similar"
    | "timeline"
    | "recommendation"
    | "terms"
    | "boot"
    | ""
  >("boot");
  const [error, setError] = useState("");
  const [lastSearchQuery, setLastSearchQuery] = useState("");
  const [selfRag, setSelfRag] = useState<SelfRagStatus | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [feedbackLoadingKey, setFeedbackLoadingKey] = useState("");
  const [productMessage, setProductMessage] = useState("");

  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedId) || documents[0],
    [documents, selectedId]
  );

  async function refresh() {
    const [healthData, documentData, traceData, requirementData] = await Promise.all([
      getHealth(),
      getDocuments(),
      getTraces(),
      getProductRequirements()
    ]);
    setHealth(healthData);
    setDocuments(documentData.documents);
    setTraces(traceData.traces);
    setRequirements(requirementData.requirements);
    if (!selectedId && documentData.documents[0]) {
      setSelectedId(documentData.documents[0].id);
    }
  }

  useEffect(() => {
    refresh()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(""));
  }, []);

  async function handleIndex() {
    setLoading("index");
    setError("");
    try {
      const result = await runIndex();
      setIndexResult(result);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  async function handleSearch() {
    if (!question.trim()) return;
    setLoading("search");
    setError("");
    try {
      const data = await search(question);
      setResults(data.results);
      setLastSearchQuery(question);
      setSelfRag(null);
      setCitationCheck(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  async function handleChat() {
    if (!question.trim()) return;
    setLoading("chat");
    setError("");
    try {
      const data = await chat(question);
      setAnswer(data.answer);
      setCitations(data.citations);
      setSelfRag(data.self_rag);
      setCitationCheck(data.citation_check || null);
      const searchData = await search(question);
      const traceData = await getTraces();
      setResults(searchData.results);
      setTraces(traceData.traces);
      setLastSearchQuery(question);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  async function handleFeedback(
    sourcePath: string,
    chunkIndex: number,
    chunkHeader: string | undefined,
    rating: 1 | -1
  ) {
    const activeQuestion = lastSearchQuery || question;
    const key = `${sourcePath}-${chunkIndex}-${rating}`;
    setFeedbackLoadingKey(key);
    setFeedbackMessage("");
    setError("");
    try {
      await submitFeedback({
        question: activeQuestion,
        source_path: sourcePath,
        chunk_index: chunkIndex,
        chunk_header: chunkHeader || "",
        rating
      });
      setFeedbackMessage(rating === 1 ? "已记录：这个片段有帮助。" : "已记录：这个片段不够相关。");
      if (lastSearchQuery) {
        const data = await search(lastSearchQuery);
        setResults(data.results);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setFeedbackLoadingKey("");
    }
  }

  async function handleAnalyzeRequirement(group: RequirementGroup) {
    setProductMessage("");
    setChangeAnalysis(null);
    if (group.versions.length < 2) {
      setProductMessage("这个需求当前只有 1 个版本，明天换办公资料后可用两个版本做变更分析。");
      return;
    }

    const [latest, previous] = group.versions;
    setLoading("product");
    setError("");
    try {
      const result = await analyzeChange(previous.document_id, latest.document_id);
      setChangeAnalysis(result);
      setProductMessage(`已分析：${group.requirement_title} 的最新两个版本。`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  async function handleLoadRequirementCard(group: RequirementGroup) {
    setProductMessage("");
    setRequirementCard(null);
    setLoading("card");
    setError("");
    try {
      const card = await getRequirementCard(group.requirement_key);
      setRequirementCard(card);
      setProductMessage(`已生成需求卡片：${group.requirement_title}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  async function handleLoadSimilarRequirements(group: RequirementGroup) {
    setProductMessage("");
    setSimilarRequirements(null);
    setLoading("similar");
    setError("");
    try {
      const result = await getSimilarRequirements(group.requirement_key, 3);
      setSimilarRequirements(result);
      setProductMessage(`已查找相似需求：${group.requirement_title}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  async function handleLoadRequirementTimeline(group: RequirementGroup) {
    setProductMessage("");
    setRequirementTimeline(null);
    setLoading("timeline");
    setError("");
    try {
      const result = await getRequirementTimeline(group.requirement_key);
      setRequirementTimeline(result);
      setProductMessage(`已生成需求演进时间线：${group.requirement_title}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  async function handleLoadSolutionRecommendation(group: RequirementGroup) {
    setProductMessage("");
    setSolutionRecommendation(null);
    setLoading("recommendation");
    setError("");
    try {
      const result = await getSolutionRecommendation(group.requirement_key);
      setSolutionRecommendation(result);
      setProductMessage(`已生成方案建议：${group.requirement_title}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  async function handleLoadTermCandidates() {
    setProductMessage("");
    setLoading("terms");
    setError("");
    try {
      const result = await getDomainTermCandidates(40);
      setTermCandidates(result);
      setProductMessage(`已挖掘术语候选：${result.candidates.length} 个`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  return (
    <main className="shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">本地 RAG 工作台</p>
          <h1>个人知识库</h1>
        </div>
        <div className="status-grid">
          <Status icon={<Server size={17} />} label="后端" value={health?.ok ? "已连接" : "未连接"} />
          <Status icon={<BookOpen size={17} />} label="文档" value={`${documents.length} 个`} />
          <Status icon={<Database size={17} />} label="切片" value={`${health?.chunk_count ?? health?.chroma_count ?? 0} 个`} />
          <Status icon={<Sparkles size={17} />} label="向量模式" value={health?.embedding_provider || "未知"} />
        </div>
      </section>

      <section className="pathbar">
        <span>{health?.docs_root || "D:\\vscode\\动效\\docs"}</span>
        <button onClick={handleIndex} disabled={loading === "index"}>
          {loading === "index" ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
          索引文档
        </button>
      </section>

      {health && !health.vector_ready && (
        <section className="notice error">
          <AlertCircle size={18} />
          <span>向量库未就绪：{health.vector_error}</span>
        </section>
      )}

      {error && (
        <section className="notice error">
          <AlertCircle size={18} />
          <span>{error}</span>
        </section>
      )}

      {indexResult && (
        <section className="notice">
          <Database size={18} />
          <span>
            已索引 {indexResult.indexed.length} 个，跳过 {indexResult.skipped.length} 个，失败 {indexResult.failed.length} 个
          </span>
        </section>
      )}

      {feedbackMessage && (
        <section className="notice">
          <ThumbsUp size={18} />
          <span>{feedbackMessage} 下次检索会参考这条反馈。</span>
        </section>
      )}

      <section className="workspace">
        <aside className="documents">
          <div className="panel-head">
            <FileText size={18} />
            <h2>文档列表</h2>
          </div>
          <div className="doc-list">
            {documents.length === 0 && <p className="empty">还没有索引文档。</p>}
            {documents.map((document) => (
              <button
                key={document.id}
                className={document.id === selectedDocument?.id ? "doc active" : "doc"}
                onClick={() => setSelectedId(document.id)}
              >
                <span className="doc-title">{document.title}</span>
                <span className="doc-meta">
                  {document.file_type} · {document.chunk_count} 个切片
                </span>
                <span className="doc-path">{shortPath(document.source_path)}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="chat-panel">
          <div className="panel-head">
            <MessageSquareText size={18} />
            <h2>提问</h2>
          </div>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
          <div className="actions">
            <button onClick={handleSearch} disabled={loading === "search"}>
              {loading === "search" ? <Loader2 className="spin" size={18} /> : <Search size={18} />}
              只检索
            </button>
            <button className="primary" onClick={handleChat} disabled={loading === "chat"}>
              {loading === "chat" ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
              AI 回答
            </button>
          </div>

          <article className="answer">
            <h3>回答</h3>
            <p>{answer || "先索引文档，再输入问题。没有配置 OPENAI_API_KEY 时，语义检索仍可用，AI 回答会显示明确的配置提示。"}</p>
          </article>

          {selfRag && (
            <article className="self-rag">
              <h3>Self-RAG 检查</h3>
              <div className="self-rag-grid">
                <span>状态</span>
                <b>{selfRagStatusLabel(selfRag.status)}</b>
                <span>初始最高分</span>
                <b>{selfRag.initial_best_score.toFixed(2)}</b>
                <span>最终最高分</span>
                <b>{selfRag.final_best_score.toFixed(2)}</b>
                <span>证据阈值</span>
                <b>{selfRag.min_evidence_score.toFixed(2)}</b>
                <span>召回方式</span>
                <b>{formatList(selfRag.retrieval_modes || []) || "未记录"}</b>
                <span>改写来源</span>
                <b>{selfRag.query_rewrite_used_llm ? "LLM 改写" : selfRag.rescue_query_source || "规则/未触发"}</b>
              </div>
              {selfRag.query_rewrite_error && <p className="diagnostic-note">{selfRag.query_rewrite_error}</p>}
              {selfRag.rescue_attempted && selfRag.rescue_queries.length > 0 && (
                <div className="rescue-queries">
                  {selfRag.rescue_queries.map((query) => (
                    <span key={query}>{query}</span>
                  ))}
                </div>
              )}
            </article>
          )}

          {citationCheck && (
            <article className={`citation-check ${citationCheck.status}`}>
              <h3>引用检查</h3>
              <div className="self-rag-grid">
                <span>状态</span>
                <b>{citationCheckStatusLabel(citationCheck.status)}</b>
                <span>支撑分</span>
                <b>{citationCheck.support_score.toFixed(2)}</b>
                <span>检查结论数</span>
                <b>{citationCheck.checked_claim_count}</b>
              </div>
              {citationCheck.reasons.length > 0 && (
                <div className="check-reasons">
                  {citationCheck.reasons.slice(0, 3).map((reason) => (
                    <span key={reason}>{reason}</span>
                  ))}
                </div>
              )}
            </article>
          )}

          <article className="citations">
            <h3>引用来源</h3>
            {citations.length === 0 && <p className="empty">还没有引用来源。</p>}
            {citations.map((citation, index) => (
              <div className="citation" key={`${citation.source_path}-${citation.chunk_index}`}>
                <b>[{index + 1}] {citation.title}</b>
                <span>
                  {citation.chunk_header ? `${citation.chunk_header} · ` : ""}
                  切片 {citation.chunk_index} · 相关度 {citation.score.toFixed(2)}
                  {citation.feedback_score ? ` · 反馈分 ${citation.feedback_score}` : ""}
                </span>
                <p>{citation.summary}</p>
                <FeedbackActions
                  sourcePath={citation.source_path}
                  chunkIndex={citation.chunk_index}
                  chunkHeader={citation.chunk_header}
                  loadingKey={feedbackLoadingKey}
                  onFeedback={handleFeedback}
                />
              </div>
            ))}
          </article>
        </section>

        <aside className="results">
          <div className="panel-head">
            <Search size={18} />
            <h2>检索结果</h2>
          </div>

          <div className="search-summary">
            {lastSearchQuery ? (
              <span>“{lastSearchQuery}” 命中 {results.length} 条</span>
            ) : (
              <span>还没有执行检索</span>
            )}
          </div>

          <div className="hit-list">
            {lastSearchQuery && results.length === 0 && <p className="empty">没有命中文档片段。</p>}
            {!lastSearchQuery && <p className="empty">检索命中的文档片段会显示在这里。</p>}
            {results.map((hit) => (
              <article className="hit" key={`${hit.metadata.source_path}-${hit.metadata.chunk_index}`}>
                <header>
                  <b>{hit.metadata.title}</b>
                  <span>{hit.score.toFixed(2)}</span>
                </header>
                <small>
                  {hit.metadata.chunk_header ? `${hit.metadata.chunk_header} · ` : ""}
                  切片 {hit.metadata.chunk_index} · {shortPath(hit.metadata.source_path)}
                </small>
                {(hit.matched_query || hit.keyword_score !== undefined) && (
                  <small>
                    {hit.retrieval_mode ? `召回：${retrievalModeLabel(hit.retrieval_mode)}` : ""}
                    {hit.keyword_backend === "fts5" ? " · BM25" : ""}
                    {hit.matched_query ? ` · 匹配问题：${hit.matched_query}` : ""}
                    {hit.keyword_score !== undefined ? ` · 关键词分 ${hit.keyword_score.toFixed(2)}` : ""}
                    {hit.keyword_recall_score ? ` · 关键词召回 ${hit.keyword_recall_score.toFixed(2)}` : ""}
                    {hit.bm25_score !== undefined ? ` · BM25 ${hit.bm25_score.toFixed(2)}` : ""}
                    {hit.bm25_bonus ? ` · BM25加分 ${hit.bm25_bonus.toFixed(2)}` : ""}
                    {hit.feedback_score ? ` · 反馈分 ${hit.feedback_score}` : ""}
                  </small>
                )}
                {hit.matched_keywords && hit.matched_keywords.length > 0 && (
                  <div className="keyword-tags">
                    {hit.matched_keywords.slice(0, 8).map((keyword) => (
                      <span key={keyword}>{keyword}</span>
                    ))}
                  </div>
                )}
                <p>{hit.content}</p>
                <FeedbackActions
                  sourcePath={hit.metadata.source_path}
                  chunkIndex={hit.metadata.chunk_index}
                  chunkHeader={hit.metadata.chunk_header}
                  loadingKey={feedbackLoadingKey}
                  onFeedback={handleFeedback}
                />
              </article>
            ))}
          </div>

          {selectedDocument && (
            <section className="preview">
              <h3>{selectedDocument.title}</h3>
              <p>{formatDate(selectedDocument.indexed_at)}</p>
              <pre>{selectedDocument.content_preview}</pre>
            </section>
          )}

          <section className="product-expert-panel">
            <h3>产品专家</h3>
            <button className="panel-action" onClick={handleLoadTermCandidates} disabled={loading === "terms"}>
              {loading === "terms" ? <Loader2 className="spin" size={15} /> : <Tags size={15} />}
              挖术语
            </button>
            {requirements.length === 0 && <p className="empty">索引文档后会在这里识别需求分组。</p>}
            {productMessage && <p className="diagnostic-note">{productMessage}</p>}
            <div className="requirement-list">
              {requirements.slice(0, 5).map((group) => (
                <article className="requirement-item" key={group.requirement_key}>
                  <header>
                    <b>{group.requirement_title}</b>
                    <span>{group.document_count} 版</span>
                  </header>
                  <small>
                    {group.project_name} · 置信度 {Math.round(group.confidence * 100)}%
                  </small>
                  {group.latest_document && (
                    <small>
                      最新：{group.latest_document.version_label} · {shortPath(group.latest_document.source_path)}
                    </small>
                  )}
                  <div className="version-tags">
                    {group.versions.slice(0, 4).map((version) => (
                      <span key={`${group.requirement_key}-${version.document_id}`}>
                        {version.is_latest ? "最新 " : ""}
                        {version.version_label}
                      </span>
                    ))}
                  </div>
                  <div className="requirement-actions">
                    <button onClick={() => handleLoadRequirementCard(group)} disabled={loading === "card"}>
                      {loading === "card" ? <Loader2 className="spin" size={15} /> : <BookOpen size={15} />}
                      查看卡片
                    </button>
                    <button onClick={() => handleLoadSimilarRequirements(group)} disabled={loading === "similar"}>
                      {loading === "similar" ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />}
                      找相似
                    </button>
                    <button onClick={() => handleLoadRequirementTimeline(group)} disabled={loading === "timeline"}>
                      {loading === "timeline" ? <Loader2 className="spin" size={15} /> : <GitBranch size={15} />}
                      看演进
                    </button>
                    <button onClick={() => handleLoadSolutionRecommendation(group)} disabled={loading === "recommendation"}>
                      {loading === "recommendation" ? <Loader2 className="spin" size={15} /> : <Lightbulb size={15} />}
                      出方案
                    </button>
                    <button onClick={() => handleAnalyzeRequirement(group)} disabled={loading === "product"}>
                      {loading === "product" ? <Loader2 className="spin" size={15} /> : <Search size={15} />}
                      分析变化
                    </button>
                  </div>
                </article>
              ))}
            </div>

            {termCandidates && (
              <article className="term-panel">
                <h3>术语候选</h3>
                <p>{termCandidates.strategy}</p>
                {termCandidates.candidates.length === 0 && <p className="empty">当前还没有可审阅的术语候选。</p>}
                <div className="term-list">
                  {termCandidates.candidates.slice(0, 12).map((candidate) => (
                    <article className="term-item" key={`${candidate.status}-${candidate.term}-${candidate.normalized}`}>
                      <header>
                        <b>{candidate.term}</b>
                        <span>{candidateStatusLabel(candidate)}</span>
                      </header>
                      <small>
                        归一：{candidate.normalized} · {candidate.category} · 置信度{" "}
                        {Math.round(candidate.confidence * 100)}%
                      </small>
                      <p>{candidate.reason}</p>
                      {candidate.matched_terms.length > 0 && (
                        <div className="version-tags">
                          {candidate.matched_terms.slice(0, 8).map((term) => (
                            <span key={`${candidate.term}-${term}`}>{term}</span>
                          ))}
                        </div>
                      )}
                      <small>来源：{candidate.sources.map(termSourceLabel).join(" / ")}</small>
                      {candidate.examples[0] && <small>样例：{candidate.examples[0]}</small>}
                    </article>
                  ))}
                </div>
              </article>
            )}

            {requirementCard && (
              <article className="requirement-card">
                <h3>需求卡片</h3>
                <p>{requirementCard.summary}</p>
                <div className={`quality-strip ${requirementCard.quality.status}`}>
                  <b>{cardQualityLabel(requirementCard.quality.status)}</b>
                  <span>完整度 {Math.round(requirementCard.quality.completeness_score * 100)}%</span>
                </div>
                <div className="keyword-tags">
                  {requirementCard.impact_modules.map((module) => (
                    <span key={module.label}>{module.label}</span>
                  ))}
                </div>
                {requirementCard.quality.missing_sections.length > 0 && (
                  <div className="version-tags">
                    {requirementCard.quality.missing_sections.map((section) => (
                      <span key={`missing-${section}`}>缺 {section}</span>
                    ))}
                  </div>
                )}
                <CardSection title="背景" items={requirementCard.sections.background || []} />
                <CardSection title="目标" items={requirementCard.sections.goals || []} />
                <CardSection title="用户/角色" items={requirementCard.sections.users || []} />
                <CardSection title="范围/功能" items={requirementCard.sections.scope || []} />
                <CardSection title="关键规则" items={requirementCard.sections.rules || []} />
                <CardSection title="风险点" items={requirementCard.sections.risks || []} />
                <CardSection title="验收点" items={requirementCard.sections.acceptance || []} />
                {requirementCard.field_facts.length > 0 && (
                  <div className="field-change-list">
                    {requirementCard.field_facts.slice(0, 6).map((fact) => (
                      <span key={`${fact.label}-${fact.value}`}>
                        {fact.label}: {fact.value}
                      </span>
                    ))}
                  </div>
                )}
                <ChangeList title="复核建议" items={requirementCard.quality.review_notes} />
                <ChangeList title="待确认" items={requirementCard.open_questions} />
                <ChangeList title="下一步" items={requirementCard.next_actions} />
              </article>
            )}

            {similarRequirements && (
              <article className="similar-panel">
                <h3>相似需求</h3>
                <p>{similarRequirements.strategy}</p>
                {similarRequirements.similar.length === 0 && <p className="empty">还没有其他需求可用于相似度比较。</p>}
                <div className="similar-list">
                  {similarRequirements.similar.map((item) => (
                    <article className="similar-item" key={item.requirement_key}>
                      <header>
                        <b>{item.requirement_title}</b>
                        <span>{Math.round(item.score * 100)}%</span>
                      </header>
                      <small>
                        {item.project_name} · {item.document_count} 版 · {item.version_label}
                      </small>
                      <p>{item.summary}</p>
                      {item.shared_modules.length > 0 && (
                        <div className="version-tags">
                          {item.shared_modules.map((module) => (
                            <span key={`${item.requirement_key}-${module}`}>{module}</span>
                          ))}
                        </div>
                      )}
                      {item.reasons.map((reason) => (
                        <small key={`${item.requirement_key}-${reason}`}>{reason}</small>
                      ))}
                    </article>
                  ))}
                </div>
              </article>
            )}

            {requirementTimeline && (
              <article className="timeline-panel">
                <h3>需求演进</h3>
                <p>{requirementTimeline.trend_summary}</p>
                <small>{requirementTimeline.strategy}</small>

                {requirementTimeline.recurring_modules.length > 0 && (
                  <div className="version-tags">
                    {requirementTimeline.recurring_modules.slice(0, 5).map((module) => (
                      <span key={module.label}>
                        {module.label} × {module.count}
                      </span>
                    ))}
                  </div>
                )}

                <div className="timeline-list">
                  {requirementTimeline.versions.map((version) => (
                    <article className={version.is_latest ? "timeline-version latest" : "timeline-version"} key={version.document.id}>
                      <header>
                        <b>
                          {version.sequence}. {version.version_label}
                        </b>
                        <span>{version.is_latest ? "最新" : `${version.line_count} 行`}</span>
                      </header>
                      <p>{version.summary}</p>
                      <small>{shortPath(version.document.source_path)}</small>
                    </article>
                  ))}
                </div>

                {requirementTimeline.change_events.length === 0 ? (
                  <p className="empty">当前只有一个版本，先补历史资料后才能看演进。</p>
                ) : (
                  <div className="timeline-list">
                    {requirementTimeline.change_events.map((event) => (
                      <article className={`timeline-change ${event.risk_level}`} key={`${event.from_version}-${event.to_version}`}>
                        <header>
                          <b>
                            {event.from_version} → {event.to_version}
                          </b>
                          <span>{riskLabel(event.risk_level)}</span>
                        </header>
                        <p>{event.summary}</p>
                        <small>
                          新增 {event.added_count} · 删除 {event.removed_count} · 字段变化 {event.field_change_count}
                        </small>
                        {event.impact_modules.length > 0 && (
                          <div className="version-tags">
                            {event.impact_modules.map((module) => (
                              <span key={`${event.sequence}-${module.label}`}>{module.label}</span>
                            ))}
                          </div>
                        )}
                        <ChangeList title="风险原因" items={event.risk_reasons} />
                        <ChangeList title="待确认" items={event.open_questions} />
                      </article>
                    ))}
                  </div>
                )}

                <ChangeList title="建议动作" items={requirementTimeline.recommendations} />
              </article>
            )}

            {solutionRecommendation && (
              <article className="recommendation-panel">
                <h3>方案建议</h3>
                <p>{solutionRecommendation.strategy}</p>
                <div className={`quality-strip ${solutionRecommendation.confidence.status}`}>
                  <b>{confidenceLabel(solutionRecommendation.confidence.status)}</b>
                  <span>置信度 {Math.round(solutionRecommendation.confidence.score * 100)}%</span>
                </div>
                <ChangeList title="置信依据" items={solutionRecommendation.confidence.reasons} />

                {solutionRecommendation.recommended_option && (
                  <article className="recommended-option">
                    <header>
                      <b>{solutionRecommendation.recommended_option.name}</b>
                      <span>{Math.round(solutionRecommendation.recommended_option.score * 100)}%</span>
                    </header>
                    <p>{solutionRecommendation.recommended_option.summary}</p>
                    <small>{solutionRecommendation.recommended_option.when_to_use}</small>
                  </article>
                )}

                <div className="option-list">
                  {solutionRecommendation.options.map((option) => (
                    <article className="option-item" key={option.name}>
                      <header>
                        <b>{option.name}</b>
                        <span>{Math.round(option.score * 100)}%</span>
                      </header>
                      <p>{option.summary}</p>
                      <ChangeList title="优点" items={option.pros} />
                      <ChangeList title="限制" items={option.cons} />
                    </article>
                  ))}
                </div>

                <div className="field-change-list">
                  {solutionRecommendation.decision_factors.map((factor) => (
                    <span key={factor.label}>
                      {factor.label}: {factor.detail}
                    </span>
                  ))}
                </div>
                <ChangeList title="风险" items={solutionRecommendation.risks} />
                <ChangeList title="验收清单" items={solutionRecommendation.acceptance_checklist} />
                <ChangeList title="待确认" items={solutionRecommendation.open_questions} />
                <ChangeList title="下一步" items={solutionRecommendation.next_steps} />

                {solutionRecommendation.evidence_refs.length > 0 && (
                  <div className="evidence-list">
                    <b>证据来源</b>
                    {solutionRecommendation.evidence_refs.map((ref) => (
                      <span key={`${ref.kind}-${ref.source_path}`}>
                        {evidenceKindLabel(ref.kind)} · {ref.title}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            )}

            {changeAnalysis && (
              <article className="change-analysis">
                <h3>变更分析</h3>
                <p>{changeAnalysis.summary}</p>
                {changeAnalysis.impact_modules.length > 0 && (
                  <div className="keyword-tags">
                    {changeAnalysis.impact_modules.map((module) => (
                      <span key={module.label}>{module.label}</span>
                    ))}
                  </div>
                )}
                <ChangeList title="新增" items={changeAnalysis.added} />
                <ChangeList title="删除" items={changeAnalysis.removed} />
                {changeAnalysis.field_changes.length > 0 && (
                  <div className="field-change-list">
                    {changeAnalysis.field_changes.slice(0, 6).map((change) => (
                      <span key={`${change.label}-${change.old_value}-${change.new_value}`}>
                        {change.label}: {change.old_value || "空"} → {change.new_value || "空"}
                      </span>
                    ))}
                  </div>
                )}
                <ChangeList title="待确认" items={changeAnalysis.open_questions} />
              </article>
            )}
          </section>

          <section className="trace-panel">
            <h3>RAG 诊断</h3>
            {traces.length === 0 && <p className="empty">还没有问答诊断记录。</p>}
            {traces.map((trace) => (
              <article
                className={trace.is_refusal || isCitationCheckRisk(trace.citation_check_status) ? "trace-item warning" : "trace-item"}
                key={trace.id}
              >
                <header>
                  <b>{selfRagStatusLabel(trace.self_rag_status)}</b>
                  <span>{trace.latency_ms}ms</span>
                </header>
                <p>{trace.question}</p>
                <small>
                  初始 {trace.initial_best_score.toFixed(2)} · 最终 {trace.final_best_score.toFixed(2)}
                  {trace.rescue_attempted ? ` · 补救${trace.rescued ? "成功" : "未命中"}` : " · 未补救"}
                  {` · 引用 ${trace.citation_count}`}
                </small>
                <small>
                  {trace.retrieval_modes.length > 0 ? `召回 ${formatList(trace.retrieval_modes)}` : "召回未记录"}
                  {trace.rescue_query_source ? ` · 改写 ${trace.query_rewrite_used_llm ? "LLM" : trace.rescue_query_source}` : ""}
                </small>
                <small>
                  引用检查 {citationCheckStatusLabel(trace.citation_check_status || "unknown")} · 支撑{" "}
                  {(trace.citation_support_score || 0).toFixed(2)} · 结论 {trace.citation_checked_claim_count || 0}
                </small>
                {trace.query_rewrite_error && <small>{trace.query_rewrite_error}</small>}
                {trace.citation_check_reasons?.[0] && <small>{trace.citation_check_reasons[0]}</small>}
                {trace.cited_titles.length > 0 && <small>{trace.cited_titles.join(" / ")}</small>}
              </article>
            ))}
          </section>
        </aside>
      </section>
    </main>
  );
}

function retrievalModeLabel(mode: string) {
  if (mode === "hybrid") return "混合";
  if (mode === "hybrid+bm25") return "混合+BM25";
  if (mode === "bm25") return "BM25";
  if (mode === "keyword") return "关键词";
  return "向量";
}

function formatList(values: string[]) {
  return values.map(retrievalModeLabel).join(" / ");
}

function selfRagStatusLabel(status: SelfRagStatus["status"] | "unknown" | string) {
  if (status === "rescued") return "二次检索后通过";
  if (status === "insufficient_after_rescue") return "补救后仍不足";
  if (status === "insufficient") return "证据不足";
  if (status === "unknown") return "未记录";
  return "证据充足";
}

function citationCheckStatusLabel(status: CitationCheck["status"] | string) {
  if (status === "supported") return "引用可支撑";
  if (status === "warning") return "支撑偏弱";
  if (status === "unsupported") return "支撑不足";
  if (status === "not_applicable") return "无需检查";
  if (status === "unknown" || !status) return "未记录";
  return status;
}

function isCitationCheckRisk(status: CitationCheck["status"] | string) {
  return status === "warning" || status === "unsupported";
}

function cardQualityLabel(status: string) {
  if (status === "good") return "卡片完整";
  if (status === "fair") return "需要复核";
  if (status === "needs_review") return "信息不足";
  return "未评估";
}

function riskLabel(level: string) {
  if (level === "high") return "高风险";
  if (level === "medium") return "中风险";
  if (level === "low") return "低风险";
  if (level === "stable") return "稳定";
  return "待判断";
}

function confidenceLabel(status: string) {
  if (status === "high") return "依据较充分";
  if (status === "medium") return "可作初稿";
  if (status === "low") return "资料不足";
  return "待判断";
}

function evidenceKindLabel(kind: string) {
  if (kind === "current_requirement") return "当前需求";
  if (kind === "similar_requirement") return "相似历史";
  if (kind === "timeline_version") return "历史版本";
  return "证据";
}

function candidateStatusLabel(candidate: DomainTermCandidate) {
  if (candidate.status === "known") return "已在词表";
  if (candidate.sources.includes("low_score_question")) return "优先复核";
  return "候选";
}

function termSourceLabel(source: string) {
  if (source === "document") return "文档";
  if (source === "low_score_question") return "低分问题";
  return source;
}

function FeedbackActions({
  sourcePath,
  chunkIndex,
  chunkHeader,
  loadingKey,
  onFeedback
}: {
  sourcePath: string;
  chunkIndex: number;
  chunkHeader?: string;
  loadingKey: string;
  onFeedback: (sourcePath: string, chunkIndex: number, chunkHeader: string | undefined, rating: 1 | -1) => void;
}) {
  const upKey = `${sourcePath}-${chunkIndex}-1`;
  const downKey = `${sourcePath}-${chunkIndex}--1`;
  return (
    <div className="feedback-actions">
      <button
        aria-label="标记这个片段有帮助"
        title="有帮助"
        disabled={loadingKey === upKey || loadingKey === downKey}
        onClick={() => onFeedback(sourcePath, chunkIndex, chunkHeader, 1)}
      >
        {loadingKey === upKey ? <Loader2 className="spin" size={15} /> : <ThumbsUp size={15} />}
      </button>
      <button
        aria-label="标记这个片段不够相关"
        title="没帮助"
        disabled={loadingKey === upKey || loadingKey === downKey}
        onClick={() => onFeedback(sourcePath, chunkIndex, chunkHeader, -1)}
      >
        {loadingKey === downKey ? <Loader2 className="spin" size={15} /> : <ThumbsDown size={15} />}
      </button>
    </div>
  );
}

function Status({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="status">
      {icon}
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function ChangeList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="change-list">
      <b>{title}</b>
      {items.slice(0, 5).map((item) => (
        <span key={`${title}-${item}`}>{item}</span>
      ))}
    </div>
  );
}

function CardSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return <ChangeList title={title} items={items} />;
}

createRoot(document.getElementById("root")!).render(<App />);
