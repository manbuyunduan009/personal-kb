export type Health = {
  ok: boolean;
  docs_root: string;
  sqlite: string;
  vector_store: string;
  embedding_provider: string;
  embedding_model: string;
  chunk_count: number;
  chroma_count: number;
  vector_ready: boolean;
  vector_error: string;
  openai_configured: boolean;
  min_evidence_score: number;
};

export type DocumentItem = {
  id: string;
  title: string;
  source_path: string;
  file_type: string;
  content_hash: string;
  last_modified: number;
  chunk_count: number;
  indexed_at: string;
  content_preview: string;
};

export type SearchHit = {
  content: string;
  metadata: {
    title: string;
    source_path: string;
    file_type: string;
    document_id: string;
    chunk_index: number;
    chunk_header?: string;
    summary: string;
  };
  distance: number;
  score: number;
  vector_score?: number;
  keyword_score?: number;
  keyword_recall_score?: number;
  keyword_backend?: string;
  bm25_score?: number;
  bm25_bonus?: number;
  matched_keywords?: string[];
  hybrid_bonus?: number;
  feedback_score?: number;
  feedback_bonus?: number;
  retrieval_mode?: "vector" | "keyword" | "hybrid";
  matched_query?: string;
};

export type Citation = {
  title: string;
  source_path: string;
  file_type: string;
  chunk_index: number;
  chunk_header?: string;
  summary: string;
  score: number;
  feedback_score?: number;
};

export type CitationCheck = {
  status: "supported" | "warning" | "unsupported" | "not_applicable" | "unknown" | string;
  support_score: number;
  reasons: string[];
  checked_claim_count: number;
};

export type SelfRagStatus = {
  status: "sufficient" | "rescued" | "insufficient" | "insufficient_after_rescue";
  rescue_attempted: boolean;
  rescued: boolean;
  rescue_queries: string[];
  rescue_query_source?: string;
  query_rewrite_used_llm?: boolean;
  query_rewrite_error?: string;
  retrieval_modes?: string[];
  initial_best_score: number;
  final_best_score: number;
  min_evidence_score: number;
  evidence_count: number;
};

export type RagTrace = {
  id: string;
  question: string;
  answer_preview: string;
  is_refusal: boolean;
  citation_count: number;
  citation_check_status: CitationCheck["status"];
  citation_support_score: number;
  citation_checked_claim_count: number;
  citation_check_reasons: string[];
  cited_titles: string[];
  self_rag_status: SelfRagStatus["status"] | "unknown";
  rescue_attempted: boolean;
  rescued: boolean;
  initial_best_score: number;
  final_best_score: number;
  min_evidence_score: number;
  evidence_count: number;
  rescue_queries: string[];
  rescue_query_source: string;
  query_rewrite_used_llm: boolean;
  query_rewrite_error: string;
  retrieval_modes: string[];
  latency_ms: number;
  created_at: string;
};

export type IndexResult = {
  docs_root: string;
  indexed: Array<{ path: string; chunks: number }>;
  skipped: Array<{ path: string; reason: string }>;
  failed: Array<{ path: string; error: string }>;
};

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getHealth() {
  return request<Health>("/api/health");
}

export function runIndex() {
  return request<IndexResult>("/api/index/run", { method: "POST" });
}

export function getDocuments() {
  return request<{ documents: DocumentItem[] }>("/api/documents");
}

export function getTraces(limit = 12) {
  return request<{ traces: RagTrace[] }>(`/api/traces?limit=${limit}`);
}

export function search(query: string, limit = 5) {
  return request<{ results: SearchHit[] }>("/api/search", {
    method: "POST",
    body: JSON.stringify({ query, limit })
  });
}

export function chat(question: string) {
  return request<{
    answer: string;
    citations: Citation[];
    self_rag: SelfRagStatus;
    citation_check?: CitationCheck;
    trace_id?: string;
  }>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ question })
  });
}

export function submitFeedback(input: {
  question: string;
  source_path: string;
  chunk_index: number;
  chunk_header?: string;
  rating: 1 | -1;
  note?: string;
}) {
  return request<{ ok: boolean }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify(input)
  });
}
