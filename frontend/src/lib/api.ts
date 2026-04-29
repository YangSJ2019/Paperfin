/** Typed API client for the Paperfin backend. */

export type PaperStatus = "pending" | "processing" | "ready" | "rejected" | "failed";

export interface PaperListItem {
  id: number;
  title: string;
  authors: string;
  score: number;
  status: PaperStatus;
  source: string;
  tags: string[];
  has_thumbnail: boolean;
}

export interface PaperDetail {
  id: number;
  title: string;
  authors: string;
  abstract: string;
  venue: string | null;
  arxiv_id: string | null;
  doi: string | null;
  summary_contribution: string;
  summary_method: string;
  summary_result: string;
  tags: string[];
  score: number;
  score_affiliation: number;
  score_author_fame: number;
  score_venue: number;
  score_llm: number;
  source: string;
  status: PaperStatus;
  error: string | null;
  has_pdf: boolean;
  has_thumbnail: boolean;
}

export interface ListPapersParams {
  minScore?: number;
  source?: string;
  sort?: "recent" | "score" | "title";
  limit?: number;
}

export interface ImportUrlResponse {
  paper_id: number | null;
  status: "queued" | "deduplicated" | "failed";
  message: string;
}

/** Thrown by the API client; exposes parsed server-side `detail` when present. */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail || `API error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      /* keep raw body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listPapers(params: ListPapersParams = {}): Promise<PaperListItem[]> {
    const qs = new URLSearchParams();
    if (params.minScore != null) qs.set("min_score", String(params.minScore));
    if (params.source) qs.set("source", params.source);
    if (params.sort) qs.set("sort", params.sort);
    if (params.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<PaperListItem[]>(`/api/papers${q ? `?${q}` : ""}`);
  },

  getPaper(id: number): Promise<PaperDetail> {
    return request<PaperDetail>(`/api/papers/${id}`);
  },

  deletePaper(id: number): Promise<void> {
    return request<void>(`/api/papers/${id}`, { method: "DELETE" });
  },

  resummarizePaper(id: number): Promise<{ paper_id: number; status: string }> {
    return request<{ paper_id: number; status: string }>(
      `/api/papers/${id}/resummarize`,
      { method: "POST" },
    );
  },

  triggerScan(): Promise<{ queued: number }> {
    return request<{ queued: number }>(`/api/papers/scan`, { method: "POST" });
  },

  importUrl(url: string): Promise<ImportUrlResponse> {
    return request<ImportUrlResponse>(`/api/papers/import-url`, {
      method: "POST",
      body: JSON.stringify({ url }),
    });
  },

  thumbnailUrl(id: number): string {
    return `/api/papers/${id}/thumbnail`;
  },

  pdfUrl(id: number): string {
    return `/api/papers/${id}/pdf`;
  },
};
