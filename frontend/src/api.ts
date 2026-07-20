import type { Analysis, IntentRestatement, Project, Rect, Revision, SampleArtwork } from "./types";

const API_ROOT = import.meta.env.VITE_API_URL ?? "/api";
const ACCESS_CODE_KEY = "artmentor_demo_access_code";

export function setDemoAccessCode(value: string): void {
  if (value.trim()) sessionStorage.setItem(ACCESS_CODE_KEY, value.trim());
  else sessionStorage.removeItem(ACCESS_CODE_KEY);
}

export function assetUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  if (API_ROOT === "/api") return path;
  return `${API_ROOT.replace(/\/api$/, "")}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const accessCode = sessionStorage.getItem(ACCESS_CODE_KEY);
  if (accessCode) headers.set("X-ArtMentor-Access-Code", accessCode);
  const response = await fetch(`${API_ROOT}${path}`, {
    credentials: "include",
    ...init,
    headers,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // 非 JSON 错误仍保留 HTTP 状态，便于前端展示。
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  session: () => request<{ ready: boolean; access_required: boolean; access_granted: boolean }>("/session"),
  samples: () => request<SampleArtwork[]>("/samples"),
  projects: () => request<Project[]>("/projects"),
  importSample: (id: string) => request<Project>(`/samples/${id}/import`, { method: "POST" }),
  createProject: (form: FormData) => request<Project>("/projects", { method: "POST", body: form }),
  restateIntent: (projectId: string) =>
    request<IntentRestatement>(`/projects/${projectId}/intent/restate`, { method: "POST" }),
  analyze: (projectId: string, confirmedIntent: string) =>
    request<Analysis>(`/projects/${projectId}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed_intent: confirmedIntent }),
    }),
  analysis: (analysisId: string) => request<Analysis>(`/analyses/${analysisId}`),
  updateAnnotation: (analysisId: string, suggestionId: string, region: Rect) =>
    request<Analysis>(`/analyses/${analysisId}/suggestions/${suggestionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ region }),
    }),
  feedback: (analysisId: string, suggestionId: string, verdict: string, reason?: string) =>
    request<{ id: string; verdict: string }>(`/analyses/${analysisId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suggestion_id: suggestionId, verdict, reason: reason || null }),
    }),
  revision: (projectId: string, analysisId: string, file: File) => {
    const form = new FormData();
    form.append("base_analysis_id", analysisId);
    form.append("image", file);
    return request<Revision>(`/projects/${projectId}/revisions`, { method: "POST", body: form });
  },
};
