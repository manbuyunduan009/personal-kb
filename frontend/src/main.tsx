import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  BookOpen,
  Database,
  FileText,
  Loader2,
  MessageSquareText,
  Play,
  Search,
  Server,
  Sparkles
} from "lucide-react";
import {
  chat,
  Citation,
  DocumentItem,
  getDocuments,
  getHealth,
  Health,
  IndexResult,
  runIndex,
  search,
  SearchHit
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
  const [results, setResults] = useState<SearchHit[]>([]);
  const [indexResult, setIndexResult] = useState<IndexResult | null>(null);
  const [loading, setLoading] = useState<"index" | "search" | "chat" | "boot" | "">("boot");
  const [error, setError] = useState("");

  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedId) || documents[0],
    [documents, selectedId]
  );

  async function refresh() {
    const [healthData, documentData] = await Promise.all([getHealth(), getDocuments()]);
    setHealth(healthData);
    setDocuments(documentData.documents);
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
      const searchData = await search(question);
      setResults(searchData.results);
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

          <article className="citations">
            <h3>引用来源</h3>
            {citations.length === 0 && <p className="empty">还没有引用来源。</p>}
            {citations.map((citation, index) => (
              <div className="citation" key={`${citation.source_path}-${citation.chunk_index}`}>
                <b>[{index + 1}] {citation.title}</b>
                <span>切片 {citation.chunk_index} · 相关度 {citation.score.toFixed(2)}</span>
                <p>{citation.summary}</p>
              </div>
            ))}
          </article>
        </section>

        <aside className="results">
          <div className="panel-head">
            <Search size={18} />
            <h2>检索结果</h2>
          </div>

          {selectedDocument && (
            <section className="preview">
              <h3>{selectedDocument.title}</h3>
              <p>{formatDate(selectedDocument.indexed_at)}</p>
              <pre>{selectedDocument.content_preview}</pre>
            </section>
          )}

          <div className="hit-list">
            {results.length === 0 && <p className="empty">检索命中的文档片段会显示在这里。</p>}
            {results.map((hit) => (
              <article className="hit" key={`${hit.metadata.source_path}-${hit.metadata.chunk_index}`}>
                <header>
                  <b>{hit.metadata.title}</b>
                  <span>{hit.score.toFixed(2)}</span>
                </header>
                <p>{hit.content}</p>
              </article>
            ))}
          </div>
        </aside>
      </section>
    </main>
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

createRoot(document.getElementById("root")!).render(<App />);
