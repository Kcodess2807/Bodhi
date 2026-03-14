const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);

  // Attach Clerk session JWT for authenticated API calls
  if (typeof window !== "undefined") {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const token = await (window as any).Clerk?.session?.getToken();
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
    } catch {
      // Silently continue — anonymous request
    }
  }

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── Roles ────────────────────────────────────────────────

export interface Role {
  id: number;
  role_name: string;
  description: string;
  focus_areas: string;
  typical_topics: string;
  created_at: string;
  updated_at: string;
}

export const listRoles = () => request<Role[]>("/api/roles");

export const createRole = (data: {
  role_name: string;
  description?: string;
  focus_areas?: string;
  typical_topics?: string;
}) =>
  request<Role>("/api/roles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const deleteRole = (name: string) =>
  request<void>(`/api/roles/${encodeURIComponent(name)}`, { method: "DELETE" });

// ── Companies ────────────────────────────────────────────

export interface CompanyProfile {
  id: number;
  company_name: string;
  role: string;
  description: string | null;
  hiring_patterns: string | null;
  tech_stack: string | null;
  contributed_by: string | null;
  updated_at: string;
}

export const listCompanies = () => request<CompanyProfile[]>("/api/companies");

export const createCompany = (data: {
  company_name: string;
  role?: string;
  description?: string;
  hiring_patterns?: string;
  tech_stack?: string;
}) =>
  request<CompanyProfile>("/api/companies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const deleteCompany = (name: string, role: string) =>
  request<void>(
    `/api/companies/${encodeURIComponent(name)}/${encodeURIComponent(role)}`,
    { method: "DELETE" }
  );

// ── Documents ────────────────────────────────────────────

export interface IngestResponse {
  chunks_ingested: number;
}
export interface UploadResponse {
  chunks_ingested: number;
  topics_extracted: string[];
}
export interface SearchResult {
  chunk_text: string;
  similarity: number;
}
export interface TopicsResponse {
  company: string;
  role: string;
  topics: string[];
}

export const ingestText = (data: {
  company: string;
  role?: string;
  text: string;
  source_label?: string;
}) =>
  request<IngestResponse>("/api/documents/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const uploadFile = (company: string, role: string, file: File) => {
  const form = new FormData();
  form.append("company", company);
  form.append("role", role);
  form.append("file", file);
  return request<UploadResponse>("/api/documents/upload", {
    method: "POST",
    body: form,
  });
};

export const searchDocs = (params: {
  company: string;
  role?: string;
  query: string;
  top_k?: number;
}) => {
  const sp = new URLSearchParams({
    company: params.company,
    role: params.role ?? "general",
    query: params.query,
  });
  if (params.top_k) sp.set("top_k", String(params.top_k));
  return request<SearchResult[]>(`/api/documents/search?${sp}`);
};

export const getTopics = (company: string, role: string) =>
  request<TopicsResponse>(
    `/api/documents/topics?company=${encodeURIComponent(company)}&role=${encodeURIComponent(role)}`
  );

// ── Resumes ──────────────────────────────────────────────

export interface CandidateProfile {
  name: string;
  email: string | null;
  phone: string | null;
  summary: string | null;
  skills: string[];
  experience: Array<{
    title: string;
    company: string;
    duration: string;
    description: string;
  }>;
  education: Array<{
    degree: string;
    institution: string;
    year: string;
  }>;
  projects: Array<{
    name: string;
    description: string;
    technologies: string[];
  }>;
}

export interface ResumeUploadResponse {
  user_id: string;
  profile: CandidateProfile;
}

export const uploadResume = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<ResumeUploadResponse>("/api/resumes/upload", {
    method: "POST",
    body: form,
  });
};

export const getResumeProfile = (userId: string) =>
  request<CandidateProfile>(`/api/resumes/${userId}`);

// ── Interviews ───────────────────────────────────────────

export interface InterviewStart {
  session_id: string;
  greeting_text: string;
  greeting_audio_b64: string;
}
export interface MessageReply {
  transcript: string;
  reply_text: string;
  reply_audio_b64: string;
  phase: string;
  should_end: boolean;
}
export interface SessionState {
  session_id: string;
  phase: string;
  difficulty_level: number;
  phase_scores: Record<string, unknown>;
  company: string;
  role: string;
}
export interface SessionEnd {
  session_id: string;
  summary: string;
  overall_score: number | null;
}

export const startInterview = (data: {
  candidate_name?: string;
  company?: string;
  role?: string;
  mode?: "standard" | "option_a" | "option_b";
  user_id?: string;
  jd_text?: string;
}) =>
  request<InterviewStart>("/api/interviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const sendMessage = (sessionId: string, text: string) =>
  request<MessageReply>(`/api/interviews/${sessionId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

export const sendAudio = (sessionId: string, blob: Blob, filename = "audio.webm") => {
  const form = new FormData();
  form.append("file", blob, filename);
  return request<MessageReply>(`/api/interviews/${sessionId}/audio`, {
    method: "POST",
    body: form,
  });
};

export const getSession = (sessionId: string) =>
  request<SessionState>(`/api/interviews/${sessionId}`);

export const endInterview = (sessionId: string) =>
  request<SessionEnd>(`/api/interviews/${sessionId}/end`, { method: "POST" });

// ── Streaming endpoints ─────────────────────────────────────────

/** Parsed metadata from streaming response headers. */
export interface StreamMeta {
  session?: string;
  text?: string;
  transcript?: string;
  phase?: string;
  shouldEnd?: boolean;
}

/** Extract X-Bodhi-* headers from a streaming response, URL-decoding values. */
export function parseStreamHeaders(res: Response): StreamMeta {
  const d = (key: string) => {
    const v = res.headers.get(`X-Bodhi-${key}`);
    return v ? decodeURIComponent(v) : undefined;
  };
  return {
    session: d("Session"),
    text: d("Text"),
    transcript: d("Transcript"),
    phase: d("Phase"),
    shouldEnd: d("End") === "true",
  };
}

/** Start interview, returning a raw streaming Response (audio/mpeg). */
export const startInterviewStream = (data: {
  candidate_name?: string;
  company?: string;
  role?: string;
  mode?: "standard" | "option_a" | "option_b";
  user_id?: string;
  jd_text?: string;
}) =>
  fetch(`${BASE}/api/interviews/start-stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

/** Send text message and receive streaming audio response. */
export const sendMessageStream = (sessionId: string, text: string) =>
  fetch(`${BASE}/api/interviews/${sessionId}/message-stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

/** Send audio blob and receive streaming audio response. */
export const sendAudioStream = (
  sessionId: string,
  blob: Blob,
  filename = "audio.webm"
) => {
  const form = new FormData();
  form.append("file", blob, filename);
  return fetch(`${BASE}/api/interviews/${sessionId}/audio-stream`, {
    method: "POST",
    body: form,
  });
};
