import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  Database,
  FileText,
  FolderOpen,
  GitBranch,
  History,
  Loader2,
  MessageSquareText,
  Search,
  Sparkles,
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
  getDocuments,
  getHealth,
  getProductRequirements,
  getRequirementCard,
  getRequirementTimeline,
  getSimilarRequirements,
  getSolutionRecommendation,
  getTraces,
  Health,
  IndexResult,
  RagTrace,
  RequirementCard,
  RequirementGroup,
  RequirementTimeline,
  runIndex,
  search,
  SearchHit,
  SelfRagStatus,
  SimilarRequirementsResult,
  SolutionRecommendation,
  submitFeedback
} from "./api";
import "./styles.css";

type Mode = "qa" | "expert";
type LoadingKey =
  | "boot"
  | "index"
  | "search"
  | "chat"
  | "expert"
  | "card"
  | "similar"
  | "timeline"
  | "recommendation"
  | "";

function App() {
  const [mode, setMode] = useState<Mode>("expert");
  const [health, setHealth] = useState<Health | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [traces, setTraces] = useState<RagTrace[]>([]);
  const [requirements, setRequirements] = useState<RequirementGroup[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedRequirementKey, setSelectedRequirementKey] = useState("");
  const [question, setQuestion] = useState("游园会的载体是啥？");
  const [productTask, setProductTask] = useState(
    "根据当前文件夹里的资料，判断这次游园会应该怎么做，和历史方案相比有哪些变化？"
  );
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [citationCheck, setCitationCheck] = useState<CitationCheck | null>(null);
  const [results, setResults] = useState<SearchHit[]>([]);
  const [selfRag, setSelfRag] = useState<SelfRagStatus | null>(null);
  const [requirementCard, setRequirementCard] = useState<RequirementCard | null>(null);
  const [similarRequirements, setSimilarRequirements] = useState<SimilarRequirementsResult | null>(null);
  const [requirementTimeline, setRequirementTimeline] = useState<RequirementTimeline | null>(null);
  const [solutionRecommendation, setSolutionRecommendation] = useState<SolutionRecommendation | null>(null);
  const [changeAnalysis, setChangeAnalysis] = useState<ChangeAnalysis | null>(null);
  const [indexResult, setIndexResult] = useState<IndexResult | null>(null);
  const [loading, setLoading] = useState<LoadingKey>("boot");
  const [error, setError] = useState("");
  const [lastSearchQuery, setLastSearchQuery] = useState("");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [feedbackLoadingKey, setFeedbackLoadingKey] = useState("");
  const [productMessage, setProductMessage] = useState("");

  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedId) || documents[0] || null,
    [documents, selectedId]
  );

  const selectedRequirement = useMemo(
    () =>
      requirements.find((requirement) => requirement.requirement_key === selectedRequirementKey) ||
      requirements[0] ||
      null,
    [requirements, selectedRequirementKey]
  );

  const folderRows = useMemo(() => buildFolderRows(documents), [documents]);
  const rootPath = health?.docs_root || "D:\\vscode\\动效\\docs";
  const latestTrace = traces[0] || null;

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
    if (!selectedRequirementKey && requirementData.requirements[0]) {
      setSelectedRequirementKey(requirementData.requirements[0].requirement_key);
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
    setMode("qa");
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
    setMode("qa");
    setLoading("chat");
    setError("");
    try {
      const data = await chat(question);
      setAnswer(data.answer);
      setCitations(data.citations);
      setSelfRag(data.self_rag);
      setCitationCheck(data.citation_check || null);
      const [searchData, traceData] = await Promise.all([search(question), getTraces()]);
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

  function clearProductOutputs() {
    setRequirementCard(null);
    setSimilarRequirements(null);
    setRequirementTimeline(null);
    setSolutionRecommendation(null);
    setChangeAnalysis(null);
  }

  async function handleRunProductExpert(group = selectedRequirement) {
    if (!group) {
      setProductMessage("没有可分析的需求。");
      return;
    }
    setMode("expert");
    setProductMessage("");
    setError("");
    setLoading("expert");
    clearProductOutputs();
    try {
      const [card, similar, timeline, recommendation] = await Promise.all([
        getRequirementCard(group.requirement_key),
        getSimilarRequirements(group.requirement_key, 3),
        getRequirementTimeline(group.requirement_key),
        getSolutionRecommendation(group.requirement_key)
      ]);
      setRequirementCard(card);
      setSimilarRequirements(similar);
      setRequirementTimeline(timeline);
      setSolutionRecommendation(recommendation);
      if (group.versions.length >= 2) {
        const [latest, previous] = group.versions;
        const change = await analyzeChange(previous.document_id, latest.document_id);
        setChangeAnalysis(change);
      }
      setProductMessage(`已基于 ${group.requirement_title} 生成方案草稿。`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  async function handleLoadProductPart(kind: "card" | "similar" | "timeline" | "recommendation") {
    if (!selectedRequirement) return;
    setMode("expert");
    setProductMessage("");
    setError("");
    setLoading(kind);
    try {
      if (kind === "card") {
        setRequirementCard(await getRequirementCard(selectedRequirement.requirement_key));
        setProductMessage("已生成需求卡片。");
      }
      if (kind === "similar") {
        setSimilarRequirements(await getSimilarRequirements(selectedRequirement.requirement_key, 3));
        setProductMessage("已找到相似历史需求。");
      }
      if (kind === "timeline") {
        setRequirementTimeline(await getRequirementTimeline(selectedRequirement.requirement_key));
        setProductMessage("已生成需求演进时间线。");
      }
      if (kind === "recommendation") {
        setSolutionRecommendation(await getSolutionRecommendation(selectedRequirement.requirement_key));
        setProductMessage("已生成方案建议。");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading("");
    }
  }

  return (
    <main className="app-shell">
      <header className="app-topbar">
        <div className="brand-block">
          <h1>网站资料问答与方案生成</h1>
        </div>
        <div className="mode-switch" aria-label="工作模式">
          <button className={mode === "expert" ? "active" : ""} onClick={() => setMode("expert")}>
            <Sparkles size={16} />
            方案生成
          </button>
          <button className={mode === "qa" ? "active" : ""} onClick={() => setMode("qa")}>
            <MessageSquareText size={16} />
            资料问答
          </button>
        </div>
      </header>

      {(error || feedbackMessage || indexResult || (health && !health.vector_ready)) && (
        <section className="notice-row">
          {health && !health.vector_ready && (
            <Notice tone="error" icon={<AlertCircle size={16} />} text={`向量库未就绪：${health.vector_error}`} />
          )}
          {error && <Notice tone="error" icon={<AlertCircle size={16} />} text={error} />}
          {feedbackMessage && <Notice icon={<ThumbsUp size={16} />} text={`${feedbackMessage} 下次检索会参考这条反馈。`} />}
          {indexResult && (
            <Notice
              icon={<Database size={16} />}
              text={`已索引 ${indexResult.indexed.length} 个，跳过 ${indexResult.skipped.length} 个，失败 ${indexResult.failed.length} 个`}
            />
          )}
        </section>
      )}

      <section className="workspace">
        <aside className="context-panel">
          <PanelTitle icon={<FolderOpen size={16} />} title="资料目录" />
          <div className="folder-card">
            <b>{rootPath}</b>
            <span>{documents.length} 个文件 · {health?.chunk_count ?? health?.chroma_count ?? 0} 个片段</span>
          </div>
          <div className="file-tree">
            {documents.length === 0 && <p className="empty">未索引</p>}
            {folderRows.map((row) => (
              <button
                key={row.id}
                className={`file-row ${row.documentId === selectedDocument?.id ? "active" : ""} ${row.kind}`}
                onClick={() => row.documentId && setSelectedId(row.documentId)}
              >
                <span>{row.title}</span>
                <small>{row.meta}</small>
              </button>
            ))}
          </div>
        </aside>

        <section className="center-workspace">
          {mode === "expert" ? (
            <ProductExpertWorkbench
              task={productTask}
              setTask={setProductTask}
              loading={loading}
              requirements={requirements}
              selectedRequirement={selectedRequirement}
              selectedRequirementKey={selectedRequirementKey}
              setSelectedRequirementKey={setSelectedRequirementKey}
              productMessage={productMessage}
              requirementCard={requirementCard}
              similarRequirements={similarRequirements}
              requirementTimeline={requirementTimeline}
              solutionRecommendation={solutionRecommendation}
              changeAnalysis={changeAnalysis}
              onRun={() => handleRunProductExpert()}
              onLoadPart={handleLoadProductPart}
            />
          ) : (
            <KnowledgeQaWorkbench
              question={question}
              setQuestion={setQuestion}
              loading={loading}
              answer={answer}
              citations={citations}
              onSearch={handleSearch}
              onChat={handleChat}
              feedbackLoadingKey={feedbackLoadingKey}
              onFeedback={handleFeedback}
            />
          )}
        </section>

        <aside className="diagnostic-panel">
          <PanelTitle icon={mode === "expert" ? <GitBranch size={16} /> : <Search size={16} />} title="来源" />
          {mode === "expert" ? (
            <ProductDiagnostics
              selectedRequirement={selectedRequirement}
              requirementCard={requirementCard}
              solutionRecommendation={solutionRecommendation}
              requirementTimeline={requirementTimeline}
              changeAnalysis={changeAnalysis}
              documents={documents}
            />
          ) : (
            <QaDiagnostics
              results={results}
              selfRag={selfRag}
              citationCheck={citationCheck}
              traces={traces}
              latestTrace={latestTrace}
              feedbackLoadingKey={feedbackLoadingKey}
              onFeedback={handleFeedback}
            />
          )}
        </aside>
      </section>
    </main>
  );
}

function ProductExpertWorkbench({
  task,
  setTask,
  loading,
  requirements,
  selectedRequirement,
  selectedRequirementKey,
  setSelectedRequirementKey,
  productMessage,
  requirementCard,
  similarRequirements,
  requirementTimeline,
  solutionRecommendation,
  changeAnalysis,
  onRun,
  onLoadPart
}: {
  task: string;
  setTask: (value: string) => void;
  loading: LoadingKey;
  requirements: RequirementGroup[];
  selectedRequirement: RequirementGroup | null;
  selectedRequirementKey: string;
  setSelectedRequirementKey: (value: string) => void;
  productMessage: string;
  requirementCard: RequirementCard | null;
  similarRequirements: SimilarRequirementsResult | null;
  requirementTimeline: RequirementTimeline | null;
  solutionRecommendation: SolutionRecommendation | null;
  changeAnalysis: ChangeAnalysis | null;
  onRun: () => void;
  onLoadPart: (kind: "card" | "similar" | "timeline" | "recommendation") => void;
}) {
  return (
    <>
      <section className="command-panel">
        <div>
          <h2>方案生成</h2>
        </div>
        <div className="requirement-select">
          <label>
            当前需求
            <select value={selectedRequirementKey} onChange={(event) => setSelectedRequirementKey(event.target.value)}>
              {requirements.length === 0 && <option value="">暂无需求</option>}
              {requirements.map((requirement) => (
                <option key={requirement.requirement_key} value={requirement.requirement_key}>
                  {requirement.requirement_title}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="task-input">
          <textarea value={task} onChange={(event) => setTask(event.target.value)} />
          <button className="primary run-button" onClick={onRun} disabled={loading === "expert"}>
            {loading === "expert" ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
            生成方案
          </button>
        </div>
      </section>

      <section className="work-area">
        <div className="work-header">
          <div>
            <h2>工作台</h2>
          </div>
          <div className="mini-actions">
            <button onClick={() => onLoadPart("card")} disabled={loading === "card"}>
              {loading === "card" ? <Loader2 className="spin" size={15} /> : <FileText size={15} />}
              需求卡片
            </button>
            <button onClick={() => onLoadPart("similar")} disabled={loading === "similar"}>
              <Search size={15} />
              相似历史
            </button>
            <button onClick={() => onLoadPart("timeline")} disabled={loading === "timeline"}>
              <History size={15} />
              演进
            </button>
            <button onClick={() => onLoadPart("recommendation")} disabled={loading === "recommendation"}>
              <Sparkles size={15} />
              方案
            </button>
          </div>
        </div>
        <div className="work-stream">
          {!requirementCard && !similarRequirements && !requirementTimeline && !solutionRecommendation && !changeAnalysis && (
            <div className="empty-state">
              <b>等待运行</b>
              <span>未运行</span>
            </div>
          )}
          {requirementCard && (
            <article className="insight">
              <header>
                <b>{requirementCard.requirement_title}</b>
                <span>{cardQualityLabel(requirementCard.quality.status)}</span>
              </header>
              <p>{requirementCard.summary}</p>
              <TagList items={requirementCard.impact_modules.map((module) => module.label)} />
            </article>
          )}
          {similarRequirements && (
            <article className="insight">
              <header>
                <b>相似历史</b>
                <span>{similarRequirements.similar.length} 条</span>
              </header>
              {similarRequirements.similar.slice(0, 3).map((item) => (
                <p key={item.requirement_key}>
                  {item.requirement_title} · {Math.round(item.score * 100)}% · {item.summary}
                </p>
              ))}
            </article>
          )}
          {requirementTimeline && (
            <article className="insight">
              <header>
                <b>需求演进</b>
                <span>{requirementTimeline.versions.length} 版</span>
              </header>
              <p>{requirementTimeline.trend_summary}</p>
              <TagList items={requirementTimeline.recurring_modules.map((module) => `${module.label} × ${module.count}`)} />
            </article>
          )}
          {changeAnalysis && (
            <article className="insight">
              <header>
                <b>变更分析</b>
                <span>{changeAnalysis.impact_modules.length} 个影响模块</span>
              </header>
              <p>{changeAnalysis.summary}</p>
              <TagList items={changeAnalysis.impact_modules.map((module) => module.label)} />
            </article>
          )}
        </div>
      </section>

      <section className="output-panel">
        <div className="output-header">
          <div>
            <h2>方案草稿</h2>
          </div>
          {productMessage && <span>{productMessage}</span>}
        </div>
        {solutionRecommendation ? (
          <div className="product-output">
            <article>
              <h3>{solutionRecommendation.recommended_option.name}</h3>
              <p>{solutionRecommendation.recommended_option.summary}</p>
              <small>{solutionRecommendation.recommended_option.when_to_use}</small>
            </article>
            <ChangeList title="决策依据" items={solutionRecommendation.decision_factors.map((factor) => `${factor.label}: ${factor.detail}`)} />
            <ChangeList title="风险" items={solutionRecommendation.risks} />
            <ChangeList title="验收重点" items={solutionRecommendation.acceptance_checklist} />
            <ChangeList title="待确认" items={solutionRecommendation.open_questions} />
            <ChangeList title="下一步" items={solutionRecommendation.next_steps} />
          </div>
        ) : (
          <div className="empty-output">
            <b>暂无输出</b>
          </div>
        )}
      </section>
    </>
  );
}

function KnowledgeQaWorkbench({
  question,
  setQuestion,
  loading,
  answer,
  citations,
  onSearch,
  onChat,
  feedbackLoadingKey,
  onFeedback
}: {
  question: string;
  setQuestion: (value: string) => void;
  loading: LoadingKey;
  answer: string;
  citations: Citation[];
  onSearch: () => void;
  onChat: () => void;
  feedbackLoadingKey: string;
  onFeedback: (sourcePath: string, chunkIndex: number, chunkHeader: string | undefined, rating: 1 | -1) => void;
}) {
  return (
    <>
      <section className="command-panel">
        <div>
          <h2>资料问答</h2>
        </div>
        <div className="task-input">
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
          <div className="vertical-actions">
            <button onClick={onSearch} disabled={loading === "search"}>
              {loading === "search" ? <Loader2 className="spin" size={18} /> : <Search size={18} />}
              只检索
            </button>
            <button className="primary" onClick={onChat} disabled={loading === "chat"}>
              {loading === "chat" ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
              生成回答
            </button>
          </div>
        </div>
      </section>

      <section className="output-panel qa-answer">
        <div className="output-header">
          <div>
            <h2>回答</h2>
          </div>
        </div>
        <p>{answer || "暂无回答"}</p>
      </section>

      <section className="work-area citation-area">
        <div className="work-header">
          <div>
            <h2>引用来源</h2>
          </div>
          <span>{citations.length} 条</span>
        </div>
        <div className="source-list">
          {citations.length === 0 && <p className="empty">暂无引用</p>}
          {citations.map((citation, index) => (
            <article className="source-item" key={`${citation.source_path}-${citation.chunk_index}`}>
              <header>
                <b>[{index + 1}] {citation.title}</b>
                <span>{citation.score.toFixed(2)}</span>
              </header>
              <small>
                {citation.chunk_header ? `${citation.chunk_header} · ` : ""}切片 {citation.chunk_index}
              </small>
              <p>{citation.summary}</p>
              <FeedbackActions
                sourcePath={citation.source_path}
                chunkIndex={citation.chunk_index}
                chunkHeader={citation.chunk_header}
                loadingKey={feedbackLoadingKey}
                onFeedback={onFeedback}
              />
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function ProductDiagnostics({
  selectedRequirement,
  requirementCard,
  solutionRecommendation,
  requirementTimeline,
  changeAnalysis,
  documents
}: {
  selectedRequirement: RequirementGroup | null;
  requirementCard: RequirementCard | null;
  solutionRecommendation: SolutionRecommendation | null;
  requirementTimeline: RequirementTimeline | null;
  changeAnalysis: ChangeAnalysis | null;
  documents: DocumentItem[];
}) {
  return (
    <div className="diagnostic-stack">
      <DiagnosticCard title="资料覆盖">
        <p>{documents.length} 个文件已进入当前知识库。</p>
        <Progress value={documents.length > 0 ? 72 : 0} />
      </DiagnosticCard>
      <DiagnosticCard title="当前需求">
        <p>{selectedRequirement ? selectedRequirement.requirement_title : "暂无需求"}</p>
        {selectedRequirement && <small>{selectedRequirement.document_count} 版 · {selectedRequirement.project_name}</small>}
      </DiagnosticCard>
      <DiagnosticCard title="引用来源">
        {solutionRecommendation?.evidence_refs.length ? (
          solutionRecommendation.evidence_refs.slice(0, 4).map((ref) => (
            <span className="line" key={`${ref.kind}-${ref.source_path}`}>{evidenceKindLabel(ref.kind)} · {ref.title}</span>
          ))
        ) : (
          <p>暂无引用</p>
        )}
      </DiagnosticCard>
      <DiagnosticCard title="当前问题" tone="warn">
        <ChangeList
          title=""
          items={[
            ...(requirementCard?.open_questions || []),
            ...(solutionRecommendation?.open_questions || []),
            ...(changeAnalysis?.open_questions || [])
          ].slice(0, 4)}
        />
        {!requirementCard && !solutionRecommendation && <p>未运行</p>}
      </DiagnosticCard>
      <DiagnosticCard title="可信度">
        <p>{solutionRecommendation ? confidenceLabel(solutionRecommendation.confidence.status) : "待判断"}</p>
        {solutionRecommendation && <Progress value={Math.round(solutionRecommendation.confidence.score * 100)} />}
      </DiagnosticCard>
      {requirementTimeline && (
        <DiagnosticCard title="历史演进">
          <p>{requirementTimeline.versions.length} 个版本，{requirementTimeline.change_events.length} 次变更。</p>
        </DiagnosticCard>
      )}
    </div>
  );
}

function QaDiagnostics({
  results,
  selfRag,
  citationCheck,
  traces,
  latestTrace,
  feedbackLoadingKey,
  onFeedback
}: {
  results: SearchHit[];
  selfRag: SelfRagStatus | null;
  citationCheck: CitationCheck | null;
  traces: RagTrace[];
  latestTrace: RagTrace | null;
  feedbackLoadingKey: string;
  onFeedback: (sourcePath: string, chunkIndex: number, chunkHeader: string | undefined, rating: 1 | -1) => void;
}) {
  return (
    <div className="diagnostic-stack">
      <DiagnosticCard title="Self-RAG">
        {selfRag ? (
          <>
            <p>{selfRagStatusLabel(selfRag.status)}</p>
            <small>最高分 {selfRag.final_best_score.toFixed(2)} / 阈值 {selfRag.min_evidence_score.toFixed(2)}</small>
            <Progress value={Math.round((selfRag.final_best_score / Math.max(selfRag.min_evidence_score, 0.01)) * 70)} />
          </>
        ) : (
          <p>暂无诊断</p>
        )}
      </DiagnosticCard>
      <DiagnosticCard title="引用检查" tone={citationCheck && isCitationCheckRisk(citationCheck.status) ? "warn" : "normal"}>
        {citationCheck ? (
          <>
            <p>{citationCheckStatusLabel(citationCheck.status)}</p>
            <small>支撑分 {citationCheck.support_score.toFixed(2)} · 结论 {citationCheck.checked_claim_count}</small>
          </>
        ) : (
          <p>问答后检查答案是否被引用支撑。</p>
        )}
      </DiagnosticCard>
      <DiagnosticCard title="检索结果">
        <div className="hit-list">
          {results.length === 0 && <p>暂无命中</p>}
          {results.slice(0, 5).map((hit) => (
            <article className="hit" key={`${hit.metadata.source_path}-${hit.metadata.chunk_index}`}>
              <header>
                <b>{hit.metadata.title}</b>
                <span>{hit.score.toFixed(2)}</span>
              </header>
              <small>{retrievalModeLabel(hit.retrieval_mode || "vector")} · 切片 {hit.metadata.chunk_index}</small>
              <p>{hit.metadata.summary || hit.content.slice(0, 100)}</p>
              <FeedbackActions
                sourcePath={hit.metadata.source_path}
                chunkIndex={hit.metadata.chunk_index}
                chunkHeader={hit.metadata.chunk_header}
                loadingKey={feedbackLoadingKey}
                onFeedback={onFeedback}
              />
            </article>
          ))}
        </div>
      </DiagnosticCard>
      <DiagnosticCard title="最近 Trace">
        {latestTrace ? (
          <>
            <p>{latestTrace.question}</p>
            <small>
              {selfRagStatusLabel(latestTrace.self_rag_status)} · {latestTrace.latency_ms}ms · 引用 {latestTrace.citation_count}
            </small>
          </>
        ) : (
          <p>暂无记录</p>
        )}
        <small>共 {traces.length} 条记录</small>
      </DiagnosticCard>
    </div>
  );
}

function PanelTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="panel-title">
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function Notice({ icon, text, tone = "normal" }: { icon: React.ReactNode; text: string; tone?: "normal" | "error" }) {
  return (
    <div className={`notice ${tone}`}>
      {icon}
      <span>{text}</span>
    </div>
  );
}

function DiagnosticCard({
  title,
  children,
  tone = "normal"
}: {
  title: string;
  children: React.ReactNode;
  tone?: "normal" | "warn";
}) {
  return (
    <article className={`diagnostic-card ${tone}`}>
      <h3>{title}</h3>
      {children}
    </article>
  );
}

function Progress({ value }: { value: number }) {
  return (
    <div className="progress" aria-label={`进度 ${Math.min(100, Math.max(0, value))}%`}>
      <span style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

function ChangeList({ title, items }: { title: string; items: string[] }) {
  const visibleItems = items.filter(Boolean).slice(0, 6);
  if (visibleItems.length === 0) return null;
  return (
    <div className="change-list">
      {title && <b>{title}</b>}
      {visibleItems.map((item) => (
        <span key={`${title}-${item}`}>{item}</span>
      ))}
    </div>
  );
}

function TagList({ items }: { items: string[] }) {
  const visibleItems = items.filter(Boolean).slice(0, 8);
  if (visibleItems.length === 0) return null;
  return (
    <div className="tag-list">
      {visibleItems.map((item) => (
        <span key={item}>{item}</span>
      ))}
    </div>
  );
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
        {loadingKey === upKey ? <Loader2 className="spin" size={14} /> : <ThumbsUp size={14} />}
      </button>
      <button
        aria-label="标记这个片段不够相关"
        title="没帮助"
        disabled={loadingKey === upKey || loadingKey === downKey}
        onClick={() => onFeedback(sourcePath, chunkIndex, chunkHeader, -1)}
      >
        {loadingKey === downKey ? <Loader2 className="spin" size={14} /> : <ThumbsDown size={14} />}
      </button>
    </div>
  );
}

function buildFolderRows(documents: DocumentItem[]) {
  const folders = new Set<string>();
  const rows: Array<{ id: string; kind: "folder" | "file"; title: string; meta: string; documentId?: string }> = [];
  documents.forEach((document) => {
    const parts = document.source_path.split(/[\\/]/).filter(Boolean);
    const folder = parts.length > 1 ? parts[parts.length - 2] : "docs";
    if (!folders.has(folder)) {
      folders.add(folder);
      rows.push({ id: `folder-${folder}`, kind: "folder", title: folder, meta: "文件夹" });
    }
    rows.push({
      id: document.id,
      kind: "file",
      title: document.title,
      meta: `${document.file_type} · ${document.chunk_count}`,
      documentId: document.id
    });
  });
  return rows;
}

function retrievalModeLabel(mode: string) {
  if (mode === "hybrid") return "混合";
  if (mode === "hybrid+bm25") return "混合+BM25";
  if (mode === "bm25") return "BM25";
  if (mode === "keyword") return "关键词";
  return "向量";
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

createRoot(document.getElementById("root")!).render(<App />);
