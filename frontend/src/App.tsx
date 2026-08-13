/**
 * 前端页面编排层。
 *
 * App 保存“上传作品 → 确认意图 → 查看点评 → 反馈/上传修改版”的页面状态，
 * 并通过 api.ts 调用后端。画布、参考作品和前后对比分别交给独立组件渲染，
 * 因此这里主要负责业务流程，不负责网络协议或 AI Prompt。
 */
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
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
  X,
} from "lucide-react";
import { api, assetUrl, setDemoAccessCode } from "./api";
import ReferenceGrid from "./components/ReferenceGrid";
import RevisionCompare from "./components/RevisionCompare";
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

function formatDate(value: string) {
  // 历史列表只显示便于扫读的月/日，完整时间仍由后端保存。
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(value));
}

function App() {
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
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [feedback, setFeedback] = useState<Record<string, string>>({});
  const [intentionalTarget, setIntentionalTarget] = useState<string | null>(null);
  const [intentionalReason, setIntentionalReason] = useState("");
  // 公网 Demo 使用访问码控制共享 AI 额度；真正的数据隔离由后端匿名 Cookie 完成。
  const [accessRequired, setAccessRequired] = useState(false);
  const [accessCode, setAccessCode] = useState("");
  const [accessBusy, setAccessBusy] = useState(false);
  // 后端部署开关决定是否展示GPU人体功能；未配置Worker时不显示失效入口。
  const [poseEnabled, setPoseEnabled] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState({
    title: "",
    stage: "Character design sketch",
    style: "Digital illustration",
    intent: "",
  });
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const previewUrl = useMemo(() => (uploadFile ? URL.createObjectURL(uploadFile) : null), [uploadFile]);

  useEffect(() => {
    // 启动时先检查访问权限，通过后再并行加载样例与当前浏览器的历史项目。
    const bootstrap = async () => {
      const session = await api.session();
      setPoseEnabled(session.pose_enabled);
      if (session.access_required && !session.access_granted) {
        setAccessRequired(true);
        return;
      }
      const [sampleData, projects] = await Promise.all([api.samples(), api.projects()]);
      setSamples(sampleData);
      setHistory(projects);
    };
    bootstrap().catch((cause: Error) => setError(cause.message));
  }, []);

  useEffect(() => () => {
    // createObjectURL 会占用浏览器内存，切换文件或离开组件时必须释放。
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  // 每次产生新项目或新点评后重新读取历史，确保侧栏与数据库一致。
  const refreshHistory = async () => setHistory(await api.projects());

  const unlockDemo = async () => {
    // 访问码验证成功后，后端还会写入 HttpOnly Cookie，供后续图片请求使用。
    if (!accessCode.trim()) return;
    setAccessBusy(true);
    setError(null);
    try {
      setDemoAccessCode(accessCode);
      const session = await api.session();
      setPoseEnabled(session.pose_enabled);
      if (!session.access_granted) throw new Error("That access code is not correct.");
      const [sampleData, projects] = await Promise.all([api.samples(), api.projects()]);
      setSamples(sampleData);
      setHistory(projects);
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
    setActiveSuggestion(null);
    setTab("critique");
    setError(null);
  };

  const applyContextDraft = (draft: IntentRestatement, declaredStage: string) => {
    // 只有模型认为动作清楚时才预填；模糊动作必须由用户选择或保持未确认。
    setIntentDraft(draft);
    setConfirmedIntent(draft.restatement);
    setConfirmedStage(declaredStage);
    setConfirmedAction(draft.action_status === "clear" ? draft.action_hypotheses[0]?.label ?? "" : "");
  };

  const loadProject = async (item: Project) => {
    setBusy("analysis");
    setError(null);
    try {
      setProject(item);
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
        setAnalysis(null);
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

  const uploadArtwork = async () => {
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
      payload.append("style", form.style);
      payload.append("intent", form.intent);
      const created = await api.createProject(payload);
      setProject(created);
      const restated = await api.restateIntent(created.id);
      applyContextDraft(restated, created.stage);
      await refreshHistory();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const importSample = async (sampleId: string) => {
    // 公共领域样例和用户上传走相同 Project/Intent/Analysis 流程，便于可靠演示。
    setBusy("upload");
    setError(null);
    try {
      const created = await api.importSample(sampleId);
      setProject(created);
      const restated = await api.restateIntent(created.id);
      applyContextDraft(restated, created.stage);
      await refreshHistory();
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
      await refreshHistory();
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
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="brand-row">
          <button className="brand" onClick={resetWorkspace} aria-label="ArtMentor home">
            <span className="brand-mark"><PenLine size={17} /></span>
            <span>ArtMentor</span>
          </button>
          <button className="mobile-close" onClick={() => setMenuOpen(false)}><X size={20} /></button>
        </div>
        <button className="new-critique" onClick={resetWorkspace}>
          <ImagePlus size={17} /> New critique
        </button>
        <div className="history-heading"><span>Recent work</span><Clock3 size={14} /></div>
        <nav className="history-list">
          {history.map((item) => (
            <button
              key={item.id}
              onClick={() => loadProject(item)}
              className={project?.id === item.id ? "active" : ""}
            >
              <img src={assetUrl(item.image_url)} alt="" />
              <span><strong>{item.title}</strong><small>{item.stage} · {formatDate(item.created_at)}</small></span>
            </button>
          ))}
          {history.length === 0 && <p className="empty-history">Your critique history will appear here.</p>}
        </nav>
        <div className="sidebar-footer">
          <span><Cloud size={15} /> AI vision</span>
          <small>Private browser workspace</small>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setMenuOpen(true)}><Menu size={20} /></button>
          <div>
            <p className="eyebrow">Intent-aware illustration critique</p>
            <h1>{project?.title || "New critique"}</h1>
          </div>
          <div className="status-pill"><span /> {busy ? "Working" : analysis ? "Analysis ready" : "Ready"}</div>
        </header>

        {error && (
          <div className="error-banner"><CircleHelp size={17} /><span>{error}</span><button onClick={() => setError(null)}><X size={16} /></button></div>
        )}

        {!project && (
          <UploadWorkspace
            form={form}
            setForm={setForm}
            uploadFile={uploadFile}
            setUploadFile={setUploadFile}
            previewUrl={previewUrl}
            fileRef={fileRef}
            samples={samples}
            busy={busy}
            onSubmit={uploadArtwork}
            onSample={importSample}
          />
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

        {project && !intentDraft && busy === "analysis" && !analysis && <LoadingAnalysis />}

        {project && analysis && (
          <div className={`analysis-layout ${tab === "pose" ? "pose-active" : ""}`}>
            {tab !== "pose" && <section className="artwork-column">
              <Suspense fallback={<div className="canvas-loading"><LoaderCircle className="spin" size={25} /> Preparing canvas…</div>}>
                <AnnotationCanvas
                  imageUrl={assetUrl(project.image_url)}
                  suggestions={analysis.result.suggestions}
                  activeId={activeSuggestion}
                  onActiveChange={setActiveSuggestion}
                  onRegionChange={updateRegion}
                />
              </Suspense>
              <div className="palette-strip">
                <span>Extracted palette</span>
                <div>{analysis.result.visual_metrics.palette.map((color) => <i key={color} style={{ background: color }} title={color} />)}</div>
                <small>{analysis.result.visual_metrics.width} × {analysis.result.visual_metrics.height}</small>
              </div>
            </section>}

            <aside className="inspector">
              <div className="tabs">
                <button className={tab === "critique" ? "active" : ""} onClick={() => setTab("critique")}>Critique</button>
                <button className={tab === "references" ? "active" : ""} onClick={() => setTab("references")}>References</button>
                {poseEnabled && (
                  <button className={tab === "pose" ? "active" : ""} onClick={() => setTab("pose")}><ScanLine size={13} /> Body structure</button>
                )}
                <button className={tab === "revision" ? "active" : ""} onClick={() => setTab("revision")}>Revision</button>
              </div>

              {tab === "critique" && analysis.result.warning && <div className="demo-notice"><Sparkles size={15} />{analysis.result.warning}</div>}

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
                  <div className="section-intro"><p className="eyebrow">Public-domain study set</p><h2>Look with a purpose.</h2><p>Each work is paired to a specific decision in your critique. Open the museum record for provenance.</p></div>
                  <ReferenceGrid references={analysis.result.references} />
                </div>
              )}
              {poseEnabled && tab === "pose" && (
                <div className="panel-scroll pose-scroll">
                  <Suspense fallback={<div className="pose-loading"><LoaderCircle className="spin" size={22} /> Loading body-check workspace…</div>}>
                    <BodyCheckPanel project={project} onError={setError} />
                  </Suspense>
                </div>
              )}
              {tab === "revision" && (
                <div className="panel-scroll revision-panel">
                  {!revision ? (
                    <label className={`revision-drop ${busy === "revision" ? "disabled" : ""}`}>
                      {busy === "revision" ? <LoaderCircle className="spin" size={28} /> : <RotateCcw size={28} />}
                      <h2>{busy === "revision" ? "Comparing versions…" : "Upload your revision"}</h2>
                      <p>ArtMentor will compare the before and after across all four dimensions.</p>
                      <span>Choose revised artwork</span>
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
  // 共享 Demo 的预算门禁；它不是用户账号系统，匿名数据隔离仍由后端负责。
  return (
    <main className="access-shell">
      <section className="access-card">
        <span className="access-icon"><LockKeyhole size={22} /></span>
        <p className="eyebrow">Private demo</p>
        <h1>Welcome to ArtMentor.</h1>
        <p>This preview uses a shared AI budget. Enter the access code provided by the creator to continue.</p>
        <form onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
          <label><span>Demo access code</span><input type="password" autoFocus value={value} onChange={(event) => onChange(event.target.value)} autoComplete="off" /></label>
          <button className="primary-action" disabled={busy || !value.trim()} type="submit">
            {busy ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
            Enter ArtMentor
          </button>
        </form>
        {error && <p className="access-error">{error}</p>}
        <small>Your code stays in this browser tab and is never included in the public source code.</small>
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
}

function UploadWorkspace({ form, setForm, uploadFile, setUploadFile, previewUrl, fileRef, samples, busy, onSubmit, onSample }: UploadProps) {
  // 首屏收集模型理解作品所需的最小上下文，也提供无需上传的公共领域样例入口。
  const update = (key: keyof UploadProps["form"], value: string) => setForm((current) => ({ ...current, [key]: value }));
  return (
    <div className="onboarding">
      <section className="onboarding-copy">
        <p className="eyebrow">A second pair of eyes, built for illustrators</p>
        <h2>Make the next revision<br />the one that matters.</h2>
        <p>ArtMentor reads your intent first, then gives a focused critique across composition, value, color, and visual narrative.</p>
        <div className="promise-row">
          <span><Target size={16} /> Three priorities, maximum</span>
          <span><PenLine size={16} /> Editable image annotations</span>
          <span><RotateCcw size={16} /> Before-and-after report</span>
        </div>
      </section>

      <section className="upload-card">
        <button className={`drop-zone ${previewUrl ? "has-image" : ""}`} onClick={() => fileRef.current?.click()}>
          {previewUrl ? <img src={previewUrl} alt="Artwork preview" /> : <><span className="upload-icon"><Upload size={22} /></span><strong>Drop your artwork here</strong><small>JPG, PNG or WebP · up to 10 MB</small></>}
          {previewUrl && <span className="change-image">Change artwork</span>}
        </button>
        <input ref={fileRef} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
        <div className="form-grid">
          <label className="full"><span>Project title <em>optional</em></span><input value={form.title} onChange={(e) => update("title", e.target.value)} placeholder={uploadFile?.name.replace(/\.[^.]+$/, "") || "Evening light study"} /></label>
          <label><span>Stage</span><select value={form.stage} onChange={(e) => update("stage", e.target.value)}>{STAGES.map((stage) => <option key={stage}>{stage}</option>)}</select></label>
          <label><span>Style</span><input value={form.style} onChange={(e) => update("style", e.target.value)} placeholder="Painterly fantasy" /></label>
          <label className="full"><span>What are you trying to communicate?</span><textarea rows={4} value={form.intent} onChange={(e) => update("intent", e.target.value)} placeholder="I want the quiet figure to feel small against the city, but still hopeful…" /></label>
        </div>
        <button className="primary-action" disabled={busy !== null} onClick={onSubmit}>
          {busy === "upload" ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
          Clarify my intent <ArrowRight size={17} />
        </button>
        <p className="upload-privacy">Your artwork is stored for your private browser history and is sent to the configured AI provider when you request the visual context check and critique.</p>
      </section>

      <section className="sample-section">
        <div><p className="eyebrow">No artwork ready?</p><h3>Try a public-domain study.</h3></div>
        <div className="sample-grid">
          {samples.map((sample) => (
            <button key={sample.id} onClick={() => onSample(sample.id)} disabled={busy !== null}>
              <img src={sample.image_url} alt={sample.title} />
              <span><strong>{sample.title}</strong><small>{sample.artist} · {sample.license}</small></span>
              <ChevronRight size={17} />
            </button>
          ))}
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
  // 把 AI 的意图复述做成可编辑门槛：用户确认后，这段文字才成为点评判断基准。
  return (
    <div className="intent-layout">
      <div className="intent-art"><img src={assetUrl(project.image_url)} alt={project.title} /><div><span>{stage}</span><span>{project.style}</span></div></div>
      <section className="intent-card">
        <div className="step-label"><span>1</span> Confirm what ArtMentor should assume</div>
        <p className="eyebrow">Before any critique</p>
        <h2>Let’s make sure we are looking at the same picture.</h2>
        <p className="intent-explainer">Confirm the stage, action, and intent first. Uncertain visual interpretations will not be treated as facts.</p>

        <div className="perception-audit">
          {draft.visual_observations.length > 0 && (
            <div className="audit-block">
              <span className="audit-label">Visible facts</span>
              {draft.visual_observations.map((observation) => <p key={observation}><Check size={14} />{observation}</p>)}
            </div>
          )}

          <label className="stage-confirmation">
            <span className="audit-label">Critique stage</span>
            <select value={stage} onChange={(event) => onStageChange(event.target.value)}>
              {STAGES.map((item) => <option key={item}>{item}</option>)}
            </select>
            <small className={`audit-status ${draft.stage_assessment}`}>{draft.stage_assessment}</small>
            {draft.stage_note && <p>{draft.stage_note}</p>}
            {draft.suggested_stage && draft.suggested_stage !== stage && STAGES.includes(draft.suggested_stage) && (
              <button className="stage-suggestion" onClick={() => onStageChange(draft.suggested_stage!)} type="button">
                Use suggested stage: {draft.suggested_stage}
              </button>
            )}
          </label>

          {draft.action_status !== "not_applicable" && (
            <div className="audit-block action-audit">
              <div className="audit-heading">
                <span className="audit-label">Character action</span>
                <small className={`audit-status ${draft.action_status}`}>{draft.action_status}</small>
              </div>
              <p className="action-question">{draft.action_question || "What should this action be read as?"}</p>
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
                    className={action === "The exact action is intentionally ambiguous." ? "selected" : ""}
                    onClick={() => onActionChange("The exact action is intentionally ambiguous.")}
                    type="button"
                  >
                    Keep it ambiguous
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
                placeholder="Describe the action, or leave blank if it should stay unknown"
              />
            </div>
          )}
        </div>

        <label className="intent-editor"><span>ArtMentor’s reading of your intent</span><textarea value={value} onChange={(event) => onChange(event.target.value)} rows={6} /></label>
        {draft.assumptions.length > 0 && <div className="assumptions"><span>Assumptions to verify</span>{draft.assumptions.map((item) => <p key={item}><Check size={14} />{item}</p>)}</div>}
        <div className="confirmation-question"><Target size={18} /><p>{draft.confirmation_question}</p></div>
        <button className="primary-action" disabled={busy !== null} onClick={onConfirm}>
          {busy === "analysis" ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
          Confirm and critique <ArrowRight size={17} />
        </button>
        <small className="model-note">
          Visual context checked by {draft.provider === "demo" ? "offline demo mode" : draft.provider === "gptsapi" ? `WildAI · ${draft.model}` : draft.model}
        </small>
      </section>
    </div>
  );
}

function LoadingAnalysis() {
  // 视觉模型调用可能需要较长时间，用明确阶段文案代替空白页面。
  return <div className="loading-analysis"><div className="orbit"><span /><span /><Sparkles size={28} /></div><p className="eyebrow">Reading the artwork</p><h2>Building a focused critique…</h2><p>Composition · Value · Color · Narrative</p></div>;
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
  // 按“总评 → 四维概览 → 三条重点建议 → 针对性练习”展示结构化结果。
  // 每条建议内部固定为术语、白话、目标和步骤，避免模型输出变成难懂的长段落。
  const result = props.analysis.result;
  return (
    <div className="panel-scroll critique-panel">
      <section className="overall-card">
        <p className="eyebrow">Overall read</p>
        <h2>{result.overall_read}</h2>
        <div className="strengths">{result.strengths.map((item) => <span key={item}><Check size={14} />{item}</span>)}</div>
      </section>

      <section className="dimension-grid">
        {result.dimensions.map((dimension) => {
          const Icon = DIMENSION_ICONS[dimension.dimension];
          return <article key={dimension.dimension}><div><Icon size={17} /><span>{dimension.dimension}</span><strong>{dimension.score}<small>/10</small></strong></div><h4>{dimension.headline}</h4></article>;
        })}
      </section>

      <section className="suggestions-section">
        <div className="section-title"><div><p className="eyebrow">Highest-leverage moves</p><h3>{result.suggestions.length} priorities for the next pass</h3></div><span>Click to locate</span></div>
        {result.suggestions.map((suggestion, index) => (
          <article key={suggestion.id} className={`suggestion-card ${props.activeSuggestion === suggestion.id ? "active" : ""}`} onClick={() => props.setActiveSuggestion(suggestion.id)}>
            <div className="suggestion-number">{String(index + 1).padStart(2, "0")}</div>
            <div className="suggestion-body">
              <div className="suggestion-meta"><span>{suggestion.dimension}</span><i>{suggestion.priority} impact</i></div>
              <h3>{suggestion.title}</h3>
              <div className="teaching-layer term-layer"><small>Art term</small><strong>{suggestion.technical_term}</strong></div>
              <div className="teaching-layer plain-layer"><small>In plain language</small><p>{suggestion.plain_explanation}</p></div>
              <div className="goal-line"><Target size={15} /><div><small>Goal</small><strong>{suggestion.goal}</strong></div></div>
              <div className="steps-block"><small>Try this</small><ol>{suggestion.steps.map((step) => <li key={step}>{step}</li>)}</ol></div>
              <div className="feedback-row" onClick={(event) => event.stopPropagation()}>
                <small>Was this useful?</small>
                <button className={props.feedback[suggestion.id] === "useful" ? "selected" : ""} onClick={() => props.sendFeedback(suggestion.id, "useful")}><ThumbsUp size={14} /> Yes</button>
                <button className={props.feedback[suggestion.id] === "not_useful" ? "selected" : ""} onClick={() => props.sendFeedback(suggestion.id, "not_useful")}><ThumbsDown size={14} /> No</button>
                <button className={props.feedback[suggestion.id] === "intentional" ? "selected" : ""} onClick={() => props.setIntentionalTarget(suggestion.id)}><Target size={14} /> Intentional</button>
              </div>
              {props.intentionalTarget === suggestion.id && (
                <div className="intentional-form" onClick={(event) => event.stopPropagation()}>
                  <textarea value={props.intentionalReason} onChange={(event) => props.setIntentionalReason(event.target.value)} placeholder="Why is this choice intentional? This becomes valuable training data." rows={3} />
                  <button onClick={() => props.sendFeedback(suggestion.id, "intentional", props.intentionalReason)}>Save reasoning</button>
                </div>
              )}
            </div>
          </article>
        ))}
      </section>

      <section className="exercise-card">
        <div className="exercise-icon"><PenLine size={20} /></div>
        <div><p className="eyebrow">Targeted practice · {result.exercise.duration_minutes} min</p><h3>{result.exercise.title}</h3><ol>{result.exercise.instructions.map((step) => <li key={step}>{step}</li>)}</ol><p className="success-signal"><Target size={15} /><span><strong>Success looks like:</strong> {result.exercise.success_signal}</span></p></div>
      </section>
    </div>
  );
}

export default App;
