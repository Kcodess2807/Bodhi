const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function getAuthHeaders(initHeaders?: HeadersInit): Promise<Headers> {
  const headers = new Headers(initHeaders);
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
  return headers;
}

async function request<T>(
  path: string,
  init?: RequestInit,
  authToken?: string
): Promise<T> {
  const headers = authToken
    ? new Headers({ ...init?.headers, Authorization: `Bearer ${authToken}` })
    : await getAuthHeaders(init?.headers);

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── Users ───────────────────────────────────────────────

export interface UserSyncResponse {
  user_id: string;
  clerk_user_id: string;
}

export interface UserStatusResponse {
  user_id: string;
  clerk_user_id: string;
  has_resume: boolean;
}

export const upsertCurrentUser = (authToken?: string) =>
  request<UserSyncResponse>(
    "/api/users/me",
    {
      method: "POST",
    },
    authToken
  );

export const getCurrentUserStatus = (authToken?: string) =>
  request<UserStatusResponse>("/api/users/me/status", undefined, authToken);

export interface InterviewHistoryItem {
  session_id: string;
  target_company: string;
  target_role: string;
  overall_score: number | null;
  started_at: string;
  ended_at: string | null;
}

export interface UserProfileResponse {
  clerk_user_id: string;
  has_resume: boolean;
  resume_data: CandidateProfile | null;
  resume_file_name: string | null;
  interview_history: InterviewHistoryItem[];
  full_name: string | null;
  experience_level: string | null;
}

export const getUserProfile = (authToken?: string) =>
  request<UserProfileResponse>("/api/users/me/profile", undefined, authToken);

export const downloadResumeBlob = async (authToken?: string) => {
  const headers: Record<string, string> = {};
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

  const res = await fetch("/api/users/me/resume/download", { headers });
  if (!res.ok) throw new Error("Failed to download resume");
  
  const blob = await res.blob();
  
  let filename = "resume.pdf";
  const disposition = res.headers.get("Content-Disposition");
  if (disposition && disposition.indexOf("filename=") !== -1) {
    const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
    if (filenameMatch && filenameMatch.length === 2) {
      filename = filenameMatch[1];
    }
  }

  return { blob, filename };
};

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
  experience_level: string;
  description: string | null;
  hiring_patterns: string | null;
  tech_stack: string | null;
  contributed_by: string | null;
  updated_at: string;
  custom_metrics?: string[] | null;
}

export const listCompanies = () => request<CompanyProfile[]>("/api/companies");

export const createCompany = (data: {
  company_name: string;
  role?: string;
  experience_level?: string;
  description?: string;
  hiring_patterns?: string;
  tech_stack?: string;
}) =>
  request<CompanyProfile>("/api/companies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const deleteCompany = (name: string, role: string, experience_level: string) =>
  request<void>(
    `/api/companies/${encodeURIComponent(name)}/${encodeURIComponent(role)}/${encodeURIComponent(experience_level)}`,
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

export const uploadResume = (file: File, authToken?: string) => {
  const form = new FormData();
  form.append("file", file);
  return request<ResumeUploadResponse>(
    "/api/resumes/upload",
    {
      method: "POST",
      body: form,
    },
    authToken
  );
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

export interface InterviewPrepare {
  session_id: string;
}

export const prepareInterview = (data: {
  candidate_name?: string;
  company?: string;
  role?: string;
  experience_level?: string;
  mode?: "standard" | "option_a";
  user_id?: string;
  jd_text?: string;
  interviewer_persona?: "bodhi" | "riya";
}) =>
  request<InterviewPrepare>("/api/interviews/prepare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const startInterview = (data: {
  candidate_name?: string;
  company?: string;
  role?: string;
  experience_level?: string;
  mode?: "standard" | "option_a";
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  sentiment?: Record<string, any>;
}

/** Extract X-Bodhi-* headers from a streaming response, URL-decoding values. */
export function parseStreamHeaders(res: Response): StreamMeta {
  const d = (key: string) => {
    const v = res.headers.get(`X-Bodhi-${key}`);
    return v ? decodeURIComponent(v) : undefined;
  };

  let sentiment: Record<string, unknown> | undefined;
  const rawSentiment = d("Sentiment");
  if (rawSentiment) {
    try {
      sentiment = JSON.parse(rawSentiment);
    } catch {
      // ignore malformed sentiment header
    }
  }

  return {
    session: d("Session"),
    text: d("Text"),
    transcript: d("Transcript"),
    phase: d("Phase"),
    shouldEnd: d("End") === "true",
    sentiment,
  };
}

/** Start interview, returning a raw streaming Response (audio/mpeg). */
export const startInterviewStream = async (data: {
  candidate_name?: string;
  company?: string;
  role?: string;
  experience_level?: string;
  mode?: "standard" | "option_a";
  user_id?: string;
  jd_text?: string;
  interviewer_persona?: "bodhi" | "riya";
  demo_mode?: boolean;
  demo_phase?: string;
}) => {
  const headers = await getAuthHeaders({ "Content-Type": "application/json" });
  
  // Use demo endpoint if demo_mode is true
  if (data.demo_mode && data.demo_phase) {
    return fetch(`${BASE}/api/interviews/demo/${data.demo_phase}/start-stream`, {
      method: "POST",
      headers,
    });
  }
  
  return fetch(`${BASE}/api/interviews/start-stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  });
};

/** Send text message and receive streaming audio response. */
export const sendMessageStream = async (sessionId: string, text: string) => {
  const headers = await getAuthHeaders({ "Content-Type": "application/json" });
  return fetch(`${BASE}/api/interviews/${sessionId}/message-stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ text }),
  });
};

/** Send audio blob and receive streaming audio response. */
export const sendAudioStream = async (
  sessionId: string,
  blob: Blob,
  filename = "audio.webm",
  editorContent?: string
) => {
  const form = new FormData();
  form.append("file", blob, filename);
  if (editorContent && editorContent.trim()) {
    form.append("editor_content", editorContent);
  }
  const headers = await getAuthHeaders();
  return fetch(`${BASE}/api/interviews/${sessionId}/audio-stream`, {
    method: "POST",
    headers,
    body: form,
  });
};


// ── Interview Reports ────────────────────────────────────

export interface InterviewReport {
  overall_grade: string;
  overall_score_pct: number;
  total_questions: number;
  phase_breakdown: Record<string, {
    score_pct: number;
    grade: string;
    questions_asked: number;
    avg_composite: number;
    metrics: {
      accuracy: number;
      depth: number;
      communication: number;
      confidence: number;
    };
    strengths: string[];
    improvements: string[];
    feedback: string[];
  }>;
  top_strengths: string[];
  top_improvements: string[];
  cross_section_insights: string[];
  proctoring_summary: {
    total_violations: number;
    session_flagged: boolean;
    high_severity_count: number;
    medium_severity_count: number;
    low_severity_count: number;
    violation_types: Record<string, number>;
    timeline: Array<{
      type: string;
      severity: string;
      message: string;
      timestamp: string;
    }>;
  };
  behavioral_summary: {
    avg_confidence_score: number;
    avg_speaking_rate: number;
    avg_filler_rate: number;
    dominant_emotion: string;
    dominant_sentiment: string;
    posture_issues: number;
    gaze_issues: number;
    behavioral_flags: string[];
    total_data_points: number;
  };
  hiring_recommendation: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  custom_metric_scores?: Record<string, any>;
  session_info: {
    candidate_name: string;
    target_company: string;
    target_role: string;
    session_id: string;
  };
}

export const getInterviewReport = (sessionId: string) =>
  request<InterviewReport>(`/api/interviews/${sessionId}/report`);

export const downloadReportPDF = async (sessionId: string) => {
  const headers = new Headers();
  if (typeof window !== "undefined") {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const token = await (window as any).Clerk?.session?.getToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
    } catch {}
  }

  const res = await fetch(`${BASE}/api/interviews/${sessionId}/report/pdf`, {
    method: "GET",
    headers,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `interview_report_${sessionId}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};


// ── Demo Mode ────────────────────────────────────────────

/** Start a demo interview locked to a specific phase. */
export const startDemoInterviewStream = async (phase: string) => {
  const headers = new Headers();
  if (typeof window !== "undefined") {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const token = await (window as any).Clerk?.session?.getToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
    } catch {}
  }
  return fetch(`${BASE}/api/interviews/demo/${phase}/start-stream`, {
    method: "POST",
    headers,
  });
};
