/**
 * 前端统一 API 客户端。
 *
 * 页面组件只调用下方 api 对象；本文件集中处理部署地址、Demo 访问码、
 * 匿名会话 Cookie、JSON 序列化和统一错误信息，避免这些细节散落在 UI 中。
 */
import type {
  Analysis,
  IntentRestatement,
  PoseComparison,
  Pose3DReconstruction,
  PoseInspection,
  PoseSkeleton,
  PoseStyleMode,
  Project,
  Rect,
  Revision,
  SampleArtwork,
} from "./types";
import { authAccessToken } from "./auth";

// 生产环境前后端同域使用 /api；本地也可通过 Vite 环境变量连接独立后端。
const API_ROOT = import.meta.env.VITE_API_URL ?? "/api";
const ACCESS_CODE_KEY = "artmentor_demo_access_code";

export function setDemoAccessCode(value: string): void {
  // 访问码只保存在当前标签页，刷新可用，关闭标签后自动消失。
  if (value.trim()) sessionStorage.setItem(ACCESS_CODE_KEY, value.trim());
  else sessionStorage.removeItem(ACCESS_CODE_KEY);
}

export function assetUrl(path: string): string {
  // 本地开发可能前后端分端口，生产环境则同域；这里统一拼接图片地址。
  if (/^https?:\/\//.test(path)) return path;
  if (API_ROOT === "/api") return path;
  return `${API_ROOT.replace(/\/api$/, "")}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // 所有接口共享同一套请求与错误处理，泛型 T 让调用方得到正确的 TypeScript 类型。
  const headers = new Headers(init?.headers);
  const accessCode = sessionStorage.getItem(ACCESS_CODE_KEY);
  if (accessCode) headers.set("X-ArtMentor-Access-Code", accessCode);
  // Session exchange and destructive account operations require a fresh Supabase
  // token. Other private calls use the bounded HttpOnly bridge issued by /session.
  if (path === "/session" || path.startsWith("/account")) {
    const accessToken = await authAccessToken();
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  }
  // credentials: include 让匿名会话 Cookie 随请求发送，后端据此隔离不同访客。
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
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export interface SessionStatus {
  ready: boolean;
  access_required: boolean;
  access_granted: boolean;
  pose_enabled: boolean;
  pose3d_enabled: boolean;
  auth_enabled: boolean;
  account_required: boolean;
  account_deletion_enabled: boolean;
  auth_user_id: string | null;
  auth_email: string | null;
  supabase_url: string | null;
  supabase_publishable_key: string | null;
  claimed_projects: number;
  daily_ai_limit: number | null;
  daily_ai_used: number;
  daily_ai_remaining: number | null;
}

async function downloadAccountExport(): Promise<void> {
  const headers = new Headers();
  const accessCode = sessionStorage.getItem(ACCESS_CODE_KEY);
  if (accessCode) headers.set("X-ArtMentor-Access-Code", accessCode);
  const accessToken = await authAccessToken();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_ROOT}/account/export`, {
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    let message = `Export failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Preserve the status-based fallback for non-JSON errors.
    }
    throw new Error(message);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? "ArtMentor-export.zip";
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// 页面组件只依赖这个对象，不直接关心 URL、Header、Cookie 和错误解析细节。
export const api = {
  // 启动与历史：判断门禁状态，读取样例和当前匿名会话的项目。
  session: () => request<SessionStatus>("/session"),
  logoutBridge: () => request<void>("/auth/logout", { method: "POST" }),
  exportAccount: downloadAccountExport,
  deleteAccount: () => request<void>("/account", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: "DELETE" }),
  }),
  samples: () => request<SampleArtwork[]>("/samples"),
  projects: () => request<Project[]>("/projects"),
  // 项目与意图：先保存作品，再单独复述意图，尚未执行正式视觉点评。
  importSample: (id: string) => request<Project>(`/samples/${id}/import`, { method: "POST" }),
  createProject: (form: FormData) => request<Project>("/projects", { method: "POST", body: form }),
  restateIntent: (projectId: string) =>
    request<IntentRestatement>(`/projects/${projectId}/intent/restate`, { method: "POST" }),
  // 点评与反馈：analyze 会触发视觉模型；标注位置和反馈会继续写回后端。
  analyze: (projectId: string, confirmedIntent: string, confirmedStage: string, actionContext?: string) =>
    request<Analysis>(`/projects/${projectId}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        confirmed_intent: confirmedIntent,
        confirmed_stage: confirmedStage,
        action_context: actionContext?.trim() || null,
      }),
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
  // 修改版上传使用 multipart/form-data，并指定它要对照的基础点评。
  revision: (projectId: string, analysisId: string, file: File) => {
    const form = new FormData();
    form.append("base_analysis_id", analysisId);
    form.append("image", file);
    return request<Revision>(`/projects/${projectId}/revisions`, { method: "POST", body: form });
  },
  // 作品人体自检：本地估计单幅作品骨架，用户确认后才运行保守的2D自洽性检查。
  poseInspection: (projectId: string) =>
    request<PoseInspection | null>(`/projects/${projectId}/pose-inspection`),
  estimatePoseInspection: (projectId: string, bbox: Rect, styleMode: PoseStyleMode) =>
    request<PoseInspection>(`/projects/${projectId}/pose-inspection/estimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bbox, style_mode: styleMode }),
    }),
  updatePoseInspection: (projectId: string, skeleton: PoseSkeleton) =>
    request<PoseInspection>(`/projects/${projectId}/pose-inspection/skeleton`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skeleton }),
    }),
  checkPoseInspection: (projectId: string) =>
    request<PoseInspection>(`/projects/${projectId}/pose-inspection/check`, {
      method: "POST",
    }),
  latestPose3D: (projectId: string) =>
    request<Pose3DReconstruction | null>(`/projects/${projectId}/pose3d/latest`),
  reconstructPose3D: (projectId: string) =>
    request<Pose3DReconstruction>(`/projects/${projectId}/pose3d/reconstruct`, {
      method: "POST",
    }),
  // 参考人体检查：参考图入库 → 双侧骨架估计 → 用户修正确认 → 确定性比较。
  createPoseComparison: (projectId: string, reference: File, styleMode: PoseStyleMode) => {
    const form = new FormData();
    form.append("reference_image", reference);
    form.append("style_mode", styleMode);
    return request<PoseComparison>(`/projects/${projectId}/pose-comparisons`, {
      method: "POST",
      body: form,
    });
  },
  latestPoseComparison: (projectId: string) =>
    request<PoseComparison | null>(`/projects/${projectId}/pose-comparisons/latest`),
  estimatePose: (comparisonId: string, artworkBbox: Rect, referenceBbox: Rect) =>
    request<PoseComparison>(`/pose-comparisons/${comparisonId}/estimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artwork_bbox: artworkBbox, reference_bbox: referenceBbox }),
    }),
  updatePoseSkeletons: (
    comparisonId: string,
    artworkSkeleton: PoseSkeleton,
    referenceSkeleton: PoseSkeleton,
  ) =>
    request<PoseComparison>(`/pose-comparisons/${comparisonId}/skeletons`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        artwork_skeleton: artworkSkeleton,
        reference_skeleton: referenceSkeleton,
      }),
    }),
  comparePose: (comparisonId: string) =>
    request<PoseComparison>(`/pose-comparisons/${comparisonId}/compare`, {
      method: "POST",
    }),
};
