/**
 * 前端页面编排层。
 *
 * App 保存“上传作品 → 确认意图 → 查看点评 → 反馈/上传修改版”的页面状态，
 * 并通过 api.ts 调用后端。画布、参考作品和前后对比分别交给独立组件渲染，
 * 因此这里主要负责业务流程，不负责网络协议或 AI Prompt。
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Cloud,
  ImagePlus,
  Layers3,
  Lightbulb,
  LoaderCircle,
  LogIn,
  LockKeyhole,
  Menu,
  MessageSquareMore,
  Palette,
  PenLine,
  RotateCcw,
  ScanLine,
  Sparkles,
  Target,
  ThumbsDown,
  ThumbsUp,
  Upload,
  UserRound,
  X,
} from "lucide-react";
import { api, assetUrl, setDemoAccessCode } from "./api";
import {
  clearDeletedAccountSession,
  configureAuth,
  currentAuth,
  listenForAuthChanges,
  signOutAccount,
} from "./auth";
import AuthDialog, { type AuthMode } from "./components/AuthDialog";
import Landing from "./components/Landing";
import ReferenceGrid from "./components/ReferenceGrid";
import RevisionCompare from "./components/RevisionCompare";
import { useLocale } from "./i18n";
import { LanguageSwitch } from "./LocaleProvider";
import type { Locale, MessageValues } from "./locale";
import type {
  Analysis,
  IntentRestatement,
  Project,
  Revision,
  SampleArtwork,
  Suggestion,
} from "./types";

// 标注画布依赖 Konva，体积较大；只在点评结果出现后再加载，缩短首屏等待时间。
const AnnotationCanvas = lazy(() => import("./components/AnnotationCanvas"));
const BodyCheckPanel = lazy(() => import("./components/BodyCheckPanel"));

// 点评完成后的右侧内容页签，以及当前正在执行的互斥异步任务。
type Tab = "critique" | "references" | "pose" | "revision";
type Busy = "upload" | "intent" | "analysis" | "revision" | null;

const DIMENSION_ICONS = {
  composition: Layers3,
  value: Lightbulb,
  color: Palette,
  narrative: MessageSquareMore,
};

// 阶段必须足够具体，后端会据此选择不同的评价 Rubric；Sketch 保留给旧项目兼容。
const STAGES = [
  "Thumbnail",
  "Gesture sketch",
  "Structure / anatomy study",
  "Character design sketch",
  "Sketch",
  "Clean line art",
  "Color rough",
  "Rendering",
  "Polishing",
];
const BODY_CHECK_STAGES = new Set([
  "Gesture sketch",
  "Structure / anatomy study",
  "Character design sketch",
]);

function defaultResultTab(stage: string, poseEnabled: boolean): Tab {
  return poseEnabled && BODY_CHECK_STAGES.has(stage) ? "pose" : "critique";
}

function formatDate(value: string, locale: Locale) {
  // 历史列表只显示便于扫读的月/日，完整时间仍由后端保存。
  return new Intl.DateTimeFormat(locale, { month: "short", day: "numeric" }).format(new Date(value));
}

function claimedNotice(count: number) {
  return count === 1
    ? { text: "One project from this browser is now saved to your account." }
    : { text: "{count} projects from this browser are now saved to your account.", values: { count } };
}

function App() {
  const { locale, t, errorText } = useLocale();
  // 顶层组件相当于轻量状态机：哪些对象存在，决定用户当前看到哪个业务阶段。
  // 这组状态描述完整业务阶段：作品 → 意图确认 → 点评 → 修改版对比。
  const [samples, setSamples] = useState<SampleArtwork[]>([]);
  const [history, setHistory] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [intentDraft, setIntentDraft] = useState<IntentRestatement | null>(null);
  const [confirmedIntent, setConfirmedIntent] = useState("");
  const [confirmedStage, setConfirmedStage] = useState("Character design sketch");
  const [confirmedAction, setConfirmedAction] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [revision, setRevision] = useState<Revision | null>(null);
  const [activeSuggestion, setActiveSuggestion] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("critique");
  const [busy, setBusy] = useState<Busy>(null);
  const [studyLoading, setStudyLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [feedback, setFeedback] = useState<Record<string, string>>({});
  const [intentionalTarget, setIntentionalTarget] = useState<string | null>(null);
  const [intentionalReason, setIntentionalReason] = useState("");
  // 公网 Demo 可暂时使用访问码控制共享预算；公开版的工作区由账户隔离。
  const [accessRequired, setAccessRequired] = useState(false);
  const [accessCode, setAccessCode] = useState("");
  const [accessBusy, setAccessBusy] = useState(false);
  // 后端部署开关决定是否展示GPU人体功能；未配置Worker时不显示失效入口。
  const [poseEnabled, setPoseEnabled] = useState(false);
  const [pose3dEnabled, setPose3dEnabled] = useState(false);
  // Supabase 负责可恢复账户；公开主页可匿名浏览，创作工作区需要登录。
  const [authEnabled, setAuthEnabled] = useState(false);
  const [accountRequired, setAccountRequired] = useState(true);
  const [accountEmail, setAccountEmail] = useState<string | null>(null);
  const [accountDeletionEnabled, setAccountDeletionEnabled] = useState(false);
  const [dailyAiLimit, setDailyAiLimit] = useState<number | null>(null);
  const [dailyAiRemaining, setDailyAiRemaining] = useState<number | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<AuthMode>("signin");
  const [authNotice, setAuthNotice] = useState<{ text: string; values?: MessageValues } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const historyTriggerRef = useRef<HTMLElement | null>(null);
  const closeHistoryRef = useRef<HTMLButtonElement>(null);

  const [form, setForm] = useState({
    title: "",
    stage: "Character design sketch",
    style: "",
    intent: "",
  });
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const previewUrl = useMemo(() => (uploadFile ? URL.createObjectURL(uploadFile) : null), [uploadFile]);
  const canWork = Boolean(accountEmail) || !accountRequired;

  const applySessionStatus = useCallback((session: Awaited<ReturnType<typeof api.session>>) => {
    setPoseEnabled(session.pose_enabled);
    setPose3dEnabled(session.pose3d_enabled);
    setAuthEnabled(session.auth_enabled);
    setAccountRequired(session.account_required);
    setAccountDeletionEnabled(session.account_deletion_enabled);
    setDailyAiLimit(session.daily_ai_limit);
    setDailyAiRemaining(session.daily_ai_remaining);
  }, []);

  const synchronizeAccount = useCallback(async () => {
    const account = await currentAuth();
    const session = await api.session();
    applySessionStatus(session);
    setAccountEmail(
      account.user?.email
      ?? session.auth_email
      ?? (session.auth_user_id ? "ArtMentor account" : null),
    );
    if (session.claimed_projects > 0) {
      setAuthNotice(claimedNotice(session.claimed_projects));
    }
    if ((!session.account_required || session.auth_user_id) && (!session.access_required || session.access_granted)) {
      setHistory(await api.projects());
    } else {
      setHistory([]);
    }
  }, [applySessionStatus]);

  useEffect(() => {
    // 启动时读取公开运行时配置，再恢复 Supabase 会话并认领当前匿名作品。
    let disposed = false;
    let stopListening: (() => void) | undefined;
    const bootstrap = async () => {
      let session = await api.session();
      applySessionStatus(session);
      if (session.auth_enabled && session.supabase_url && session.supabase_publishable_key) {
        configureAuth(session.supabase_url, session.supabase_publishable_key);
        const account = await currentAuth();
        if (account.session) {
          // 第二次会话请求携带已恢复的 Bearer Token，并在后端认领匿名作品。
          session = await api.session();
          applySessionStatus(session);
        } else if (session.auth_user_id) {
          // 部分浏览器会阻止 Supabase 恢复本地存储；此时继续使用后端已签名、
          // 有限时效的 HttpOnly 会话，而不是在刷新时把有效登录主动清除。
        }
        setAccountEmail(
          account.user?.email
          ?? session.auth_email
          ?? (session.auth_user_id ? "ArtMentor account" : null),
        );
        if (account.session && new URLSearchParams(window.location.search).get("auth") === "recovery") {
          setAuthMode("reset");
          setAuthOpen(true);
        }
        if (session.claimed_projects > 0) {
          setAuthNotice(claimedNotice(session.claimed_projects));
        }
        stopListening = listenForAuthChanges((event) => {
          if (event === "PASSWORD_RECOVERY") {
            setAuthMode("reset");
            setAuthOpen(true);
          }
          if (["SIGNED_IN", "SIGNED_OUT", "TOKEN_REFRESHED", "USER_UPDATED"].includes(event)) {
            // Supabase warns against awaiting other auth calls inside this callback.
            window.setTimeout(() => {
              if (disposed) return;
              void synchronizeAccount().catch((cause: Error) => setError(cause.message));
            }, 0);
          }
        });
      }
      if (session.access_required && !session.access_granted) {
        setAccessRequired(true);
        return;
      }
      setSamples(await api.samples());
      setHistory(!session.account_required || session.auth_user_id ? await api.projects() : []);
    };
    bootstrap().catch((cause: Error) => setError(cause.message));
    return () => {
      disposed = true;
      stopListening?.();
    };
  }, [applySessionStatus, synchronizeAccount]);

  useEffect(() => () => {
    // createObjectURL 会占用浏览器内存，切换文件或离开组件时必须释放。
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => {
    if (!menuOpen) return;
    const trigger = historyTriggerRef.current;
    closeHistoryRef.current?.focus();
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", dismiss);
    return () => {
      window.removeEventListener("keydown", dismiss);
      if (trigger?.isConnected && trigger.getClientRects().length) trigger.focus();
    };
  }, [menuOpen]);

  const openHistory = (trigger: HTMLElement) => {
    historyTriggerRef.current = trigger;
    setMenuOpen(true);
  };

  const unlockDemo = async () => {
    // 访问码验证成功后，后端还会写入 HttpOnly Cookie，供后续图片请求使用。
    if (!accessCode.trim()) return;
    setAccessBusy(true);
    setError(null);
    try {
      setDemoAccessCode(accessCode);
      const session = await api.session();
      applySessionStatus(session);
      if (!session.access_granted) throw new Error("That access code is not correct.");
      setSamples(await api.samples());
      setHistory(!session.account_required || session.auth_user_id ? await api.projects() : []);
      setAccessRequired(false);
    } catch (cause) {
      setDemoAccessCode("");
      setError((cause as Error).message);
    } finally {
      setAccessBusy(false);
    }
  };

  const resetWorkspace = () => {
    // 只清空当前工作区，不删除服务器中的历史项目。
    setProject(null);
    setIntentDraft(null);
    setConfirmedIntent("");
    setConfirmedStage("Character design sketch");
    setConfirmedAction("");
    setAnalysis(null);
    setRevision(null);
    setUploadFile(null);
    setForm({ title: "", stage: "Character design sketch", style: "", intent: "" });
    setActiveSuggestion(null);
    setTab("critique");
    setError(null);
    setMenuOpen(false);
  };

  const goHome = () => {
    resetWorkspace();
    window.scrollTo({ top: 0 });
  };

  const openUpload = () => {
    resetWorkspace();
    requestAnimationFrame(() => document.getElementById("upload")?.scrollIntoView({ block: "start" }));
  };

  const openAccount = () => {
    setAuthMode(accountEmail ? "account" : "signin");
    setAuthOpen(true);
  };

  const requireSignIn = () => {
    setAuthMode("signin");
    setAuthOpen(true);
  };

  const logout = async () => {
    // 先撤销 FastAPI 的媒体桥接 Cookie，再清除 Supabase 的可刷新会话。
    await api.logoutBridge();
    await signOutAccount();
    setAccountEmail(null);
    setDailyAiRemaining(null);
    resetWorkspace();
    setHistory([]);
    setAuthNotice({ text: "Signed out. Sign in again whenever you want to create or open work." });
  };

  const deleteCurrentAccount = async () => {
    await api.deleteAccount();
    await clearDeletedAccountSession();
    setAccountEmail(null);
    setDailyAiRemaining(null);
    setHistory([]);
    resetWorkspace();
    setAuthNotice({ text: "Your account and ArtMentor data were permanently deleted." });
  };

  const applyContextDraft = (draft: IntentRestatement, declaredStage: string) => {
    // 只有模型认为动作清楚时才预填；模糊动作必须由用户选择或保持未确认。
    setIntentDraft(draft);
    setConfirmedIntent(draft.restatement);
    setConfirmedStage(declaredStage);
    setConfirmedAction(draft.action_status === "clear" ? draft.action_hypotheses[0]?.label ?? "" : "");
  };

  const loadProject = async (item: Project) => {
    if (busy) return;
    setBusy(item.latest_analysis_id ? "analysis" : "intent");
    setError(null);
    try {
      setProject(item);
      setAnalysis(null);
      setActiveSuggestion(null);
      setConfirmedIntent(item.intent_confirmed || item.intent_original);
      setConfirmedStage(item.stage);
      setConfirmedAction("");
      setIntentDraft(null);
      setRevision(null);
      setTab("critique");
      // 有历史点评就直接恢复；否则从“复述意图”阶段继续，避免重复调用点评模型。
      if (item.latest_analysis_id) {
        const loaded = await api.analysis(item.latest_analysis_id);
        setAnalysis(loaded);
        const restoredStage = loaded.result.confirmed_stage || item.stage;
        setConfirmedStage(restoredStage);
        setConfirmedAction(loaded.result.confirmed_action || "");
        setActiveSuggestion(loaded.result.suggestions[0]?.id ?? null);
        setTab(defaultResultTab(restoredStage, poseEnabled));
      } else {
        const restated = await api.restateIntent(item.id);
        applyContextDraft(restated, item.stage);
      }
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
      setMenuOpen(false);
    }
  };

  const loadStudy = async (url: string, title: string, style: string, intent: string) => {
    if (busy || studyLoading) return;
    setStudyLoading(true);
    setError(null);
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error();
      const blob = await response.blob();
      if (blob.type !== "image/webp") throw new Error();
      setUploadFile(new File([blob], `${title}.webp`, { type: blob.type }));
      setForm({ title, stage: "Rendering", style, intent });
      document.getElementById("upload")?.scrollIntoView({ block: "start" });
    } catch {
      setError("Could not load this study. Please try again.");
      document.getElementById("upload")?.scrollIntoView({ block: "start" });
    } finally {
      setStudyLoading(false);
    }
  };

  const uploadArtwork = async () => {
    if (!canWork) {
      requireSignIn();
      return;
    }
    if (!uploadFile || form.intent.trim().length < 8) {
      setError("Add an artwork and describe what you want the viewer to feel or notice.");
      return;
    }
    setBusy("upload");
    setError(null);
    try {
      // 先建立 Project，再让 AI 复述意图；用户确认之前不会进入正式点评。
      const payload = new FormData();
      payload.append("image", uploadFile);
      payload.append("title", form.title || uploadFile.name.replace(/\.[^.]+$/, ""));
      payload.append("stage", form.stage);
      payload.append("style", form.style.trim() || "Digital illustration");
      payload.append("intent", form.intent);
      const created = await api.createProject(payload);
      setProject(created);
      window.scrollTo({ top: 0 });
      const restated = await api.restateIntent(created.id);
      applyContextDraft(restated, created.stage);
      await synchronizeAccount();
      window.scrollTo({ top: 0 });
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const importSample = async (sampleId: string) => {
    if (!canWork) {
      requireSignIn();
      return;
    }
    // 公共领域样例和用户上传走相同 Project/Intent/Analysis 流程，便于可靠演示。
    setBusy("upload");
    setError(null);
    try {
      const created = await api.importSample(sampleId);
      setProject(created);
      window.scrollTo({ top: 0 });
      const restated = await api.restateIntent(created.id);
      applyContextDraft(restated, created.stage);
      await synchronizeAccount();
      window.scrollTo({ top: 0 });
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const runAnalysis = async () => {
    if (!project || confirmedIntent.trim().length < 8) return;
    setBusy("analysis");
    setError(null);
    try {
      // confirmedIntent 是用户可编辑后的版本，也是后端点评时的最高优先级上下文。
      const result = await api.analyze(project.id, confirmedIntent, confirmedStage, confirmedAction);
      setAnalysis(result);
      setIntentDraft(null);
      setActiveSuggestion(result.result.suggestions[0]?.id ?? null);
      setTab(defaultResultTab(confirmedStage, poseEnabled));
      await synchronizeAccount();
      window.scrollTo({ top: 0 });
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const updateRegion = (id: string, region: Suggestion["region"]) => {
    if (!analysis) return;
    // 先更新本地画布保证拖拽流畅，再异步持久化归一化坐标。
    setAnalysis({
      ...analysis,
      result: {
        ...analysis.result,
        suggestions: analysis.result.suggestions.map((item) => (item.id === id ? { ...item, region } : item)),
      },
    });
    api.updateAnnotation(analysis.id, id, region).catch((cause: Error) => setError(cause.message));
  };

  const sendFeedback = async (suggestionId: string, verdict: string, reason?: string) => {
    if (!analysis) return;
    try {
      // “Intentional + reason”是研究风格选择与技术失误边界的关键数据。
      await api.feedback(analysis.id, suggestionId, verdict, reason);
      setFeedback((current) => ({ ...current, [suggestionId]: verdict }));
      setIntentionalTarget(null);
      setIntentionalReason("");
    } catch (cause) {
      setError((cause as Error).message);
    }
  };

  const uploadRevision = async (file: File) => {
    // 后端同时读取原图和修改版，返回四维变化报告；前端只切换到对比页展示。
    if (!project || !analysis) return;
    setBusy("revision");
    setError(null);
    try {
      const result = await api.revision(project.id, analysis.id, file);
      setRevision(result);
      setTab("revision");
      await synchronizeAccount();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (accessRequired) {
    // 公网实例配置访问码时，先渲染独立门禁页，不加载任何私人项目。
    return (
      <AccessGate
        value={accessCode}
        onChange={setAccessCode}
        onSubmit={unlockDemo}
        busy={accessBusy}
        error={error}
      />
    );
  }

  return (
    <div className={`app-shell${project ? "" : " is-landing"}`}>
      {menuOpen && <button type="button" tabIndex={-1} className="history-scrim" aria-label={t("Close recent work")} onClick={() => setMenuOpen(false)} />}
      <aside id="recent-work" className={`sidebar ${menuOpen ? "open" : ""}`} role={menuOpen ? "dialog" : undefined} aria-modal={menuOpen || undefined} aria-label={t("Recent work")} inert={authOpen}>
        <div className="brand-row">
          <button className="brand" disabled={busy !== null} onClick={goHome} aria-label={t("ArtMentor home")}>
            <span className="brand-mark"><PenLine size={17} /></span>
            <span>ArtMentor</span>
          </button>
          <button ref={closeHistoryRef} className="mobile-close" onClick={() => setMenuOpen(false)} aria-label={t("Close recent work")}><X size={20} /></button>
        </div>
        <button className="new-critique" disabled={busy !== null} onClick={openUpload}>
          <ImagePlus size={17} /> {" "}{t("New critique")}
        </button>
        <div className="history-heading"><span>{t("Recent work")}</span><Clock3 size={14} /></div>
        <nav className="history-list">
          {history.map((item) => (
            <button
              key={item.id}
              disabled={busy !== null}
              onClick={() => loadProject(item)}
              className={project?.id === item.id ? "active" : ""}
            >
              <img src={assetUrl(item.image_url)} alt="" />
              <span><strong>{item.title}</strong><small>{t(item.stage)} · {formatDate(item.created_at, locale)}</small></span>
            </button>
          ))}
          {history.length === 0 && <p className="empty-history">{t("Your critique history will appear here.")}</p>}
        </nav>
        <div className="sidebar-footer">
          <span><Cloud size={15} /> {accountEmail ? t("Account sync on") : t("AI vision")}</span>
          <small>{accountEmail ?? t(accountRequired ? "Sign in to create critiques" : "Local workspace")}</small>
        </div>
      </aside>

      <main className="workspace" inert={menuOpen || authOpen}>
        <header className={`topbar${project ? "" : " landing-topbar"}`}>
          {project ? (
            <>
              <button className="mobile-menu" aria-label={t("Open recent work")} aria-expanded={menuOpen} aria-controls="recent-work" onClick={(event) => openHistory(event.currentTarget)}><Menu size={20} /></button>
              <div className="workspace-title">
                <p className="eyebrow">{t("Intent-aware illustration critique")}</p>
                <h1>{project.title}</h1>
              </div>
            </>
          ) : (
            <>
              <a href="#top" className="brand landing-brand" aria-label={t("ArtMentor home")}>
                <span className="brand-mark"><PenLine size={17} /></span>
                <span>ArtMentor</span>
              </a>
              <nav className="landing-nav" aria-label={t("Main navigation")}>
                <a href="#how-it-works">{t("How it works")}</a>
                <a href="#gallery">{t("Examples")}</a>
              </nav>
            </>
          )}
          <div className="topbar-actions">
            {!project && canWork && (
              <button className="account-trigger history-trigger" aria-label={t("Open recent work")} aria-expanded={menuOpen} aria-controls="recent-work" onClick={(event) => openHistory(event.currentTarget)}>
                <Clock3 size={16} /> <span>{t("My work")}</span>
              </button>
            )}
            <LanguageSwitch />
            {authEnabled && (
              <button className={`account-trigger ${accountEmail ? "signed-in" : ""}`} disabled={busy !== null} onClick={openAccount} title={accountEmail ?? t("Sign in to sync your work")}>
                {accountEmail ? <UserRound size={16} /> : <LogIn size={16} />}
                <span>{accountEmail ? accountEmail.split("@")[0] : t("Sign in")}</span>
              </button>
            )}
            {project && <div className="status-pill" role="status"><span /> {busy ? t("Working") : analysis ? t("Analysis ready") : t("Ready")}</div>}
          </div>
        </header>

        {authNotice && (
          <div className="success-banner" role="status"><UserRound size={17} /><span>{t(authNotice.text, authNotice.values)}</span><button aria-label={t("Dismiss message")} onClick={() => setAuthNotice(null)}><X size={16} /></button></div>
        )}

        {error && project && (
          <div className="error-banner" role="alert"><CircleHelp size={17} /><span>{errorText(error)}</span><button aria-label={t("Dismiss message")} onClick={() => setError(null)}><X size={16} /></button></div>
        )}

        {!project && (
          <div id="top">
            <Landing locale={locale} onTryStudy={loadStudy} busy={busy !== null || studyLoading}>
              <UploadWorkspace
                form={form}
                setForm={setForm}
                uploadFile={uploadFile}
                setUploadFile={setUploadFile}
                previewUrl={previewUrl}
                fileRef={fileRef}
                samples={samples}
                busy={busy}
                disabled={studyLoading}
                error={error ? errorText(error) : null}
                onDismissError={() => setError(null)}
                canWork={canWork}
                onSubmit={uploadArtwork}
                onSample={importSample}
                onRequireSignIn={requireSignIn}
              />
            </Landing>
          </div>
        )}

        {project && intentDraft && (
          <IntentConfirmation
            project={project}
            draft={intentDraft}
            value={confirmedIntent}
            onChange={setConfirmedIntent}
            stage={confirmedStage}
            onStageChange={setConfirmedStage}
            action={confirmedAction}
            onActionChange={setConfirmedAction}
            busy={busy}
            onConfirm={runAnalysis}
          />
        )}

        {project && !intentDraft && busy && !analysis && <LoadingAnalysis readingIntent={busy !== "analysis"} />}

        {project && !intentDraft && !busy && !analysis && (
          <section className="workspace-retry">
            <h2>{t("Resume this project")}</h2>
            <p>{t("Your artwork is saved. You can retry opening the next step.")}</p>
            <button type="button" className="primary-action" onClick={() => void loadProject(project)}>
              <RotateCcw size={16} /> {t("Retry")}
            </button>
          </section>
        )}

        {project && analysis && (
          <div className={`analysis-layout ${tab === "pose" ? "pose-active" : ""}`}>
            {tab !== "pose" && <section className="artwork-column">
              <Suspense fallback={<div className="canvas-loading"><LoaderCircle className="spin" size={25} /> {" "}{t("Preparing canvas…")}</div>}>
                <AnnotationCanvas
                  imageUrl={assetUrl(project.image_url)}
                  suggestions={analysis.result.suggestions}
                  activeId={activeSuggestion}
                  onActiveChange={setActiveSuggestion}
                  onRegionChange={updateRegion}
                />
              </Suspense>
              <div className="palette-strip">
                <span>{t("Extracted palette")}</span>
                <div>{analysis.result.visual_metrics.palette.map((color) => <i key={color} style={{ background: color }} title={color} />)}</div>
                <small>{analysis.result.visual_metrics.width} × {analysis.result.visual_metrics.height}</small>
              </div>
            </section>}

            <aside className="inspector">
              <div className="tabs">
                <button className={tab === "critique" ? "active" : ""} onClick={() => setTab("critique")}>{t("Critique")}</button>
                <button className={tab === "references" ? "active" : ""} onClick={() => setTab("references")}>{t("References")}</button>
                {poseEnabled && (
                  <button className={tab === "pose" ? "active" : ""} onClick={() => setTab("pose")}><ScanLine size={13} /> {" "}{t("Body structure")}</button>
                )}
                <button className={tab === "revision" ? "active" : ""} onClick={() => setTab("revision")}>{t("Revision")}</button>
              </div>

              {tab === "critique" && analysis.result.warning && <div className="demo-notice"><Sparkles size={15} />{errorText(analysis.result.warning)}</div>}

              {tab === "critique" && (
                <CritiquePanel
                  analysis={analysis}
                  activeSuggestion={activeSuggestion}
                  setActiveSuggestion={setActiveSuggestion}
                  feedback={feedback}
                  sendFeedback={sendFeedback}
                  intentionalTarget={intentionalTarget}
                  setIntentionalTarget={setIntentionalTarget}
                  intentionalReason={intentionalReason}
                  setIntentionalReason={setIntentionalReason}
                />
              )}
              {tab === "references" && (
                <div className="panel-scroll">
                  <div className="section-intro"><p className="eyebrow">{t("Public-domain study set")}</p><h2>{t("Look with a purpose.")}</h2><p>{t("Each work is paired to a specific decision in your critique. Open the museum record for provenance.")}</p></div>
                  <ReferenceGrid references={analysis.result.references} />
                </div>
              )}
              {poseEnabled && tab === "pose" && (
                <div className="panel-scroll pose-scroll">
                  <Suspense fallback={<div className="pose-loading"><LoaderCircle className="spin" size={22} /> {" "}{t("Loading body-check workspace…")}</div>}>
                    <BodyCheckPanel
                      project={project}
                      pose3dEnabled={pose3dEnabled}
                      onError={setError}
                    />
                  </Suspense>
                </div>
              )}
              {tab === "revision" && (
                <div className="panel-scroll revision-panel">
                  {!revision ? (
                    <label className={`revision-drop ${busy === "revision" ? "disabled" : ""}`}>
                      {busy === "revision" ? <LoaderCircle className="spin" size={28} /> : <RotateCcw size={28} />}
                      <h2>{busy === "revision" ? t("Comparing versions…") : t("Upload your revision")}</h2>
                      <p>{t("ArtMentor will compare the before and after across all four dimensions.")}</p>
                      <span>{t("Choose revised artwork")}</span>
                      <input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy === "revision"} onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) uploadRevision(file);
                      }} />
                    </label>
                  ) : (
                    <RevisionCompare
                      beforeUrl={assetUrl(project.image_url)}
                      afterUrl={assetUrl(revision.image_url)}
                      comparison={revision.comparison}
                    />
                  )}
                </div>
              )}
            </aside>
          </div>
        )}
      </main>
      <AuthDialog
        open={authOpen}
        mode={authMode}
        accountEmail={accountEmail}
        dailyAiLimit={dailyAiLimit}
        dailyAiRemaining={dailyAiRemaining}
        deletionEnabled={accountDeletionEnabled}
        onModeChange={setAuthMode}
        onClose={() => setAuthOpen(false)}
        onAccountChanged={synchronizeAccount}
        onSignOut={logout}
        onExport={api.exportAccount}
        onDelete={deleteCurrentAccount}
      />
    </div>
  );
}

function AccessGate({ value, onChange, onSubmit, busy, error }: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy: boolean;
  error: string | null;
}) {
  const { t, errorText } = useLocale();
  // 共享 Demo 的预算门禁；它不是用户账号系统，匿名数据隔离仍由后端负责。
  return (
    <main className="access-shell">
      <section className="access-card">
        <LanguageSwitch />
        <span className="access-icon"><LockKeyhole size={22} /></span>
        <p className="eyebrow">{t("Private demo")}</p>
        <h1>{t("Welcome to ArtMentor.")}</h1>
        <p>{t("This preview uses a shared AI budget. Enter the access code provided by the creator to continue.")}</p>
        <form onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
          <label><span>{t("Demo access code")}</span><input type="password" autoFocus value={value} onChange={(event) => onChange(event.target.value)} autoComplete="off" /></label>
          <button className="primary-action" disabled={busy || !value.trim()} type="submit">
            {busy ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
            {t("Enter ArtMentor")}
          </button>
        </form>
        {error && <p className="access-error" role="alert">{errorText(error)}</p>}
        <small>{t("Your code stays in this browser tab and is never included in the public source code.")}</small>
      </section>
    </main>
  );
}

interface UploadProps {
  form: { title: string; stage: string; style: string; intent: string };
  setForm: React.Dispatch<React.SetStateAction<UploadProps["form"]>>;
  uploadFile: File | null;
  setUploadFile: (file: File | null) => void;
  previewUrl: string | null;
  fileRef: React.RefObject<HTMLInputElement | null>;
  samples: SampleArtwork[];
  busy: Busy;
  onSubmit: () => void;
  onSample: (id: string) => void;
  canWork: boolean;
  disabled: boolean;
  error: string | null;
  onDismissError: () => void;
  onRequireSignIn: () => void;
}

function UploadWorkspace({ form, setForm, uploadFile, setUploadFile, previewUrl, fileRef, samples, busy, disabled, error, onDismissError, onSubmit, onSample, canWork, onRequireSignIn }: UploadProps) {
  const { t } = useLocale();
  const [dragging, setDragging] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const waiting = disabled || busy !== null;
  const invalidFile = Boolean(fileError && !uploadFile);
  const update = (key: keyof UploadProps["form"], value: string) => setForm((current) => ({ ...current, [key]: value }));
  const selectFile = (file?: File) => {
    if (!file) return;
    const supported = file.type
      ? /^image\/(jpeg|png|webp)$/.test(file.type)
      : /\.(jpe?g|png|webp)$/i.test(file.name);
    if (!supported || file.size > 10 * 1024 * 1024) {
      setUploadFile(null);
      setFileError("Choose a JPG, PNG or WebP file under 10 MB.");
      return;
    }
    setFileError(null);
    setUploadFile(file);
  };
  return (
    <div className="onboarding">
      <form className="upload-card" onSubmit={(event) => {
        event.preventDefault();
        if (!waiting && !invalidFile) (canWork ? onSubmit : onRequireSignIn)();
      }}>
        <div className="upload-media">
          <button
            type="button"
            className={`drop-zone ${previewUrl ? "has-image" : ""}${dragging ? " is-dragging" : ""}`}
            disabled={waiting}
            onClick={() => canWork ? fileRef.current?.click() : onRequireSignIn()}
            onDragOver={(event) => { event.preventDefault(); if (!waiting) setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              if (waiting) return;
              if (!canWork) onRequireSignIn();
              else selectFile(event.dataTransfer.files[0]);
            }}
          >
            {previewUrl ? <img src={previewUrl} alt={t("Artwork preview")} /> : <><span className="upload-icon"><Upload size={22} /></span><strong>{t("Choose or drop your artwork")}</strong><small>{t("JPG, PNG or WebP · up to 10 MB")}</small></>}
            {previewUrl && <span className="change-image">{t("Change artwork")}</span>}
          </button>
          <input ref={fileRef} hidden type="file" accept="image/jpeg,image/png,image/webp" disabled={!canWork || waiting} onChange={(event) => {
            selectFile(event.target.files?.[0]);
            event.target.value = "";
          }} />
          {fileError && invalidFile && <p className="upload-file-error" role="alert">{t(fileError)}</p>}
        </div>
        <div className="form-grid">
          <label className="full"><span>{t("Project title")}{" "} <em>{t("optional")}</em></span><input value={form.title} onChange={(e) => update("title", e.target.value)} placeholder={uploadFile?.name.replace(/\.[^.]+$/, "") || t("Evening light study")} /></label>
          <label><span>{t("Stage")}</span><select value={form.stage} onChange={(e) => update("stage", e.target.value)}>{STAGES.map((stage) => <option key={stage} value={stage}>{t(stage)}</option>)}</select></label>
          <label><span>{t("Style")}</span><input value={form.style} onChange={(e) => update("style", e.target.value)} placeholder={t("Painterly fantasy")} /></label>
          <label className="full"><span>{t("What are you trying to communicate?")}</span><textarea rows={4} value={form.intent} onChange={(e) => update("intent", e.target.value)} placeholder={t("I want the quiet figure to feel small against the city, but still hopeful…")} /></label>
          {error && (
            <div className="error-banner upload-error" role="alert">
              <CircleHelp size={17} /><span>{error}</span>
              <button type="button" aria-label={t("Dismiss message")} onClick={onDismissError}><X size={16} /></button>
            </div>
          )}
          <button type="submit" className="primary-action" disabled={waiting || invalidFile}>
            {waiting ? <LoaderCircle className="spin" size={18} /> : canWork ? <Sparkles size={18} /> : <LogIn size={18} />}
            {t(canWork ? "Clarify my intent" : "Sign in to start")} <ArrowRight size={17} />
          </button>
          <p className="upload-privacy">{t("Your artwork is stored in your private account history and is sent to the configured AI provider only when you request a visual check, critique, or revision comparison.")}</p>
        </div>
      </form>

      {samples.length > 0 && <section className="sample-section">
        <div><p className="eyebrow">{t("No artwork ready?")}</p><h3>{t("Try a public-domain study.")}</h3></div>
        <div className="sample-grid">
          {samples.map((sample) => (
            <button key={sample.id} onClick={() => canWork ? onSample(sample.id) : onRequireSignIn()} disabled={waiting}>
              <img src={assetUrl(sample.image_url)} alt="" loading="lazy" />
              <span><strong>{sample.title}</strong><small>{sample.artist} · {sample.license}</small></span>
              <ChevronRight size={17} />
            </button>
          ))}
        </div>
      </section>}

      <section className="privacy-notice" aria-labelledby="privacy-title">
        <LockKeyhole size={20} />
        <div>
          <p className="eyebrow">{t("Privacy at a glance")}</p>
          <h3 id="privacy-title">{t("Your work stays attached to your account.")}</h3>
          <p>{t("ArtMentor stores your uploads, critique history, feedback, revision comparisons, and daily usage count. Your email and password authentication are handled by Supabase. Images and the intent you provide are sent to the configured AI provider only when you ask for an AI-powered action. You can download a ZIP of your data or permanently delete your account and stored work from the account menu.")}</p>
        </div>
      </section>
    </div>
  );
}

function IntentConfirmation({ project, draft, value, onChange, stage, onStageChange, action, onActionChange, busy, onConfirm }: {
  project: Project;
  draft: IntentRestatement;
  value: string;
  onChange: (value: string) => void;
  stage: string;
  onStageChange: (value: string) => void;
  action: string;
  onActionChange: (value: string) => void;
  busy: Busy;
  onConfirm: () => void;
}) {
  const { t } = useLocale();
  // 把 AI 的意图复述做成可编辑门槛：用户确认后，这段文字才成为点评判断基准。
  return (
    <div className="intent-layout">
      <div className="intent-art"><img src={assetUrl(project.image_url)} alt={project.title} /><div><span>{t(stage)}</span><span>{t(project.style)}</span></div></div>
      <section className="intent-card">
        <div className="step-label"><span>1</span> {" "}{t("Confirm what ArtMentor should assume")}</div>
        <p className="eyebrow">{t("Before any critique")}</p>
        <h2>{t("Let’s make sure we are looking at the same picture.")}</h2>
        <p className="intent-explainer">{t("Confirm the stage, action, and intent first. Uncertain visual interpretations will not be treated as facts.")}</p>

        <div className="perception-audit">
          {draft.visual_observations.length > 0 && (
            <div className="audit-block">
              <span className="audit-label">{t("Visible facts")}</span>
              {draft.visual_observations.map((observation) => <p key={observation}><Check size={14} />{observation}</p>)}
            </div>
          )}

          <label className="stage-confirmation">
            <span className="audit-label">{t("Critique stage")}</span>
            <select value={stage} onChange={(event) => onStageChange(event.target.value)}>
              {STAGES.map((item) => <option key={item} value={item}>{t(item)}</option>)}
            </select>
            <small className={`audit-status ${draft.stage_assessment}`}>{t(draft.stage_assessment)}</small>
            {draft.stage_note && <p>{draft.stage_note}</p>}
            {draft.suggested_stage && draft.suggested_stage !== stage && STAGES.includes(draft.suggested_stage) && (
              <button className="stage-suggestion" onClick={() => onStageChange(draft.suggested_stage!)} type="button">
                {t("Use suggested stage:")} {t(draft.suggested_stage)}
              </button>
            )}
          </label>

          {draft.action_status !== "not_applicable" && (
            <div className="audit-block action-audit">
              <div className="audit-heading">
                <span className="audit-label">{t("Character action")}</span>
                <small className={`audit-status ${draft.action_status}`}>{t(draft.action_status)}</small>
              </div>
              <p className="action-question">{draft.action_question || t("What should this action be read as?")}</p>
              {draft.action_hypotheses.length > 0 && (
                <div className="action-options">
                  {draft.action_hypotheses.map((hypothesis) => (
                    <button
                      key={hypothesis.label}
                      className={action === hypothesis.label ? "selected" : ""}
                      onClick={() => onActionChange(hypothesis.label)}
                      title={hypothesis.visible_evidence}
                      type="button"
                    >
                      {hypothesis.label}
                    </button>
                  ))}
                  <button
                    className={action === "The exact action is intentionally ambiguous." || action === "这个动作有意保持模糊。" ? "selected" : ""}
                    onClick={() => onActionChange(t("The exact action is intentionally ambiguous."))}
                    type="button"
                  >
                    {t("Keep it ambiguous")}
                  </button>
                </div>
              )}
              {draft.action_status === "ambiguous" && draft.action_hypotheses.length > 0 && (
                <div className="hypothesis-evidence">
                  {draft.action_hypotheses.map((hypothesis) => (
                    <p key={hypothesis.label}><strong>{hypothesis.label}</strong>{hypothesis.visible_evidence}</p>
                  ))}
                </div>
              )}
              <input
                className="action-context-input"
                value={action}
                onChange={(event) => onActionChange(event.target.value)}
                placeholder={t("Describe the action, or leave blank if it should stay unknown")}
              />
            </div>
          )}
        </div>

        <label className="intent-editor"><span>{t("ArtMentor’s reading of your intent")}</span><textarea value={value} onChange={(event) => onChange(event.target.value)} rows={6} /></label>
        {draft.assumptions.length > 0 && <div className="assumptions"><span>{t("Assumptions to verify")}</span>{draft.assumptions.map((item) => <p key={item}><Check size={14} />{item}</p>)}</div>}
        <div className="confirmation-question"><Target size={18} /><p>{draft.confirmation_question}</p></div>
        <button className="primary-action" disabled={busy !== null} onClick={onConfirm}>
          {busy === "analysis" ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
          {t("Confirm and critique")}{" "} <ArrowRight size={17} />
        </button>
        <small className="model-note">
          {t("Visual context checked by {model}", { model: draft.provider === "demo" ? t("offline demo mode") : draft.provider === "gptsapi" ? `WildAI · ${draft.model}` : draft.model })}
        </small>
      </section>
    </div>
  );
}

function LoadingAnalysis({ readingIntent }: { readingIntent: boolean }) {
  const { t } = useLocale();
  // 视觉模型调用可能需要较长时间，用明确阶段文案代替空白页面。
  return <div className="loading-analysis" role="status"><div className="orbit"><span /><span /><Sparkles size={28} /></div><p className="eyebrow">{t("Reading the artwork")}</p><h2>{t(readingIntent ? "Checking visual context…" : "Building a focused critique…")}</h2><p>{t("Composition · Value · Color · Narrative")}</p></div>;
}

interface CritiquePanelProps {
  analysis: Analysis;
  activeSuggestion: string | null;
  setActiveSuggestion: (id: string) => void;
  feedback: Record<string, string>;
  sendFeedback: (id: string, verdict: string, reason?: string) => void;
  intentionalTarget: string | null;
  setIntentionalTarget: (id: string | null) => void;
  intentionalReason: string;
  setIntentionalReason: (value: string) => void;
}

function CritiquePanel(props: CritiquePanelProps) {
  const { t } = useLocale();
  // 按“总评 → 四维概览 → 三条重点建议 → 针对性练习”展示结构化结果。
  // 每条建议内部固定为术语、白话、目标和步骤，避免模型输出变成难懂的长段落。
  const result = props.analysis.result;
  return (
    <div className="panel-scroll critique-panel">
      <section className="overall-card">
        <p className="eyebrow">{t("Overall read")}</p>
        <h2>{result.overall_read}</h2>
        <div className="strengths">{result.strengths.map((item) => <span key={item}><Check size={14} />{item}</span>)}</div>
      </section>

      <section className="dimension-grid">
        {result.dimensions.map((dimension) => {
          const Icon = DIMENSION_ICONS[dimension.dimension];
          return <article key={dimension.dimension}><div><Icon size={17} /><span>{t(dimension.dimension)}</span><strong>{dimension.score}<small>/10</small></strong></div><h4>{dimension.headline}</h4></article>;
        })}
      </section>

      <section className="suggestions-section">
        <div className="section-title"><div><p className="eyebrow">{t("Highest-leverage moves")}</p><h3>{t("{count} priorities for the next pass", { count: result.suggestions.length })}</h3></div><span>{t("Click to locate")}</span></div>
        {result.suggestions.map((suggestion, index) => (
          <article key={suggestion.id} className={`suggestion-card ${props.activeSuggestion === suggestion.id ? "active" : ""}`} onClick={() => props.setActiveSuggestion(suggestion.id)}>
            <div className="suggestion-number">{String(index + 1).padStart(2, "0")}</div>
            <div className="suggestion-body">
              <div className="suggestion-meta"><span>{t(suggestion.dimension)}</span><i>{t("{priority} impact", { priority: t(suggestion.priority) })}</i></div>
              <h3>{suggestion.title}</h3>
              <div className="teaching-layer term-layer"><small>{t("Art term")}</small><strong>{suggestion.technical_term}</strong></div>
              <div className="teaching-layer plain-layer"><small>{t("In plain language")}</small><p>{suggestion.plain_explanation}</p></div>
              <div className="goal-line"><Target size={15} /><div><small>{t("Goal")}</small><strong>{suggestion.goal}</strong></div></div>
              <div className="steps-block"><small>{t("Try this")}</small><ol>{suggestion.steps.map((step) => <li key={step}>{step}</li>)}</ol></div>
              <div className="feedback-row" onClick={(event) => event.stopPropagation()}>
                <small>{t("Was this useful?")}</small>
                <button className={props.feedback[suggestion.id] === "useful" ? "selected" : ""} onClick={() => props.sendFeedback(suggestion.id, "useful")}><ThumbsUp size={14} /> {" "}{t("Yes")}</button>
                <button className={props.feedback[suggestion.id] === "not_useful" ? "selected" : ""} onClick={() => props.sendFeedback(suggestion.id, "not_useful")}><ThumbsDown size={14} /> {" "}{t("No")}</button>
                <button className={props.feedback[suggestion.id] === "intentional" ? "selected" : ""} onClick={() => props.setIntentionalTarget(suggestion.id)}><Target size={14} /> {" "}{t("Intentional")}</button>
              </div>
              {props.intentionalTarget === suggestion.id && (
                <div className="intentional-form" onClick={(event) => event.stopPropagation()}>
                  <textarea value={props.intentionalReason} onChange={(event) => props.setIntentionalReason(event.target.value)} placeholder={t("Why is this choice intentional? This becomes valuable training data.")} rows={3} />
                  <button onClick={() => props.sendFeedback(suggestion.id, "intentional", props.intentionalReason)}>{t("Save reasoning")}</button>
                </div>
              )}
            </div>
          </article>
        ))}
      </section>

      <section className="exercise-card">
        <div className="exercise-icon"><PenLine size={20} /></div>
        <div><p className="eyebrow">{t("Targeted practice · {minutes} min", { minutes: result.exercise.duration_minutes })}</p><h3>{result.exercise.title}</h3><ol>{result.exercise.instructions.map((step) => <li key={step}>{step}</li>)}</ol><p className="success-signal"><Target size={15} /><span><strong>{t("Success looks like:")}</strong> {result.exercise.success_signal}</span></p></div>
      </section>
    </div>
  );
}

export default App;
