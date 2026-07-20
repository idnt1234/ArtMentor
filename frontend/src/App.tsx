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

const AnnotationCanvas = lazy(() => import("./components/AnnotationCanvas"));

type Tab = "critique" | "references" | "revision";
type Busy = "upload" | "intent" | "analysis" | "revision" | null;

const DIMENSION_ICONS = {
  composition: Layers3,
  value: Lightbulb,
  color: Palette,
  narrative: MessageSquareMore,
};

const STAGES = ["Thumbnail", "Sketch", "Color rough", "Rendering", "Polishing"];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(value));
}

function App() {
  const [samples, setSamples] = useState<SampleArtwork[]>([]);
  const [history, setHistory] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [intentDraft, setIntentDraft] = useState<IntentRestatement | null>(null);
  const [confirmedIntent, setConfirmedIntent] = useState("");
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
  const [accessRequired, setAccessRequired] = useState(false);
  const [accessCode, setAccessCode] = useState("");
  const [accessBusy, setAccessBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState({
    title: "",
    stage: "Sketch",
    style: "Digital illustration",
    intent: "",
  });
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const previewUrl = useMemo(() => (uploadFile ? URL.createObjectURL(uploadFile) : null), [uploadFile]);

  useEffect(() => {
    const bootstrap = async () => {
      const session = await api.session();
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
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const refreshHistory = async () => setHistory(await api.projects());

  const unlockDemo = async () => {
    if (!accessCode.trim()) return;
    setAccessBusy(true);
    setError(null);
    try {
      setDemoAccessCode(accessCode);
      const session = await api.session();
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
    setProject(null);
    setIntentDraft(null);
    setConfirmedIntent("");
    setAnalysis(null);
    setRevision(null);
    setUploadFile(null);
    setActiveSuggestion(null);
    setTab("critique");
    setError(null);
  };

  const loadProject = async (item: Project) => {
    setBusy("analysis");
    setError(null);
    try {
      setProject(item);
      setConfirmedIntent(item.intent_confirmed || item.intent_original);
      setIntentDraft(null);
      setRevision(null);
      setTab("critique");
      if (item.latest_analysis_id) {
        const loaded = await api.analysis(item.latest_analysis_id);
        setAnalysis(loaded);
        setActiveSuggestion(loaded.result.suggestions[0]?.id ?? null);
      } else {
        setAnalysis(null);
        const restated = await api.restateIntent(item.id);
        setIntentDraft(restated);
        setConfirmedIntent(restated.restatement);
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
      const payload = new FormData();
      payload.append("image", uploadFile);
      payload.append("title", form.title || uploadFile.name.replace(/\.[^.]+$/, ""));
      payload.append("stage", form.stage);
      payload.append("style", form.style);
      payload.append("intent", form.intent);
      const created = await api.createProject(payload);
      setProject(created);
      const restated = await api.restateIntent(created.id);
      setIntentDraft(restated);
      setConfirmedIntent(restated.restatement);
      await refreshHistory();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const importSample = async (sampleId: string) => {
    setBusy("upload");
    setError(null);
    try {
      const created = await api.importSample(sampleId);
      setProject(created);
      const restated = await api.restateIntent(created.id);
      setIntentDraft(restated);
      setConfirmedIntent(restated.restatement);
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
      const result = await api.analyze(project.id, confirmedIntent);
      setAnalysis(result);
      setIntentDraft(null);
      setActiveSuggestion(result.result.suggestions[0]?.id ?? null);
      await refreshHistory();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const updateRegion = (id: string, region: Suggestion["region"]) => {
    if (!analysis) return;
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
      await api.feedback(analysis.id, suggestionId, verdict, reason);
      setFeedback((current) => ({ ...current, [suggestionId]: verdict }));
      setIntentionalTarget(null);
      setIntentionalReason("");
    } catch (cause) {
      setError((cause as Error).message);
    }
  };

  const uploadRevision = async (file: File) => {
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
            busy={busy}
            onConfirm={runAnalysis}
          />
        )}

        {project && !intentDraft && busy === "analysis" && !analysis && <LoadingAnalysis />}

        {project && analysis && (
          <div className="analysis-layout">
            <section className="artwork-column">
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
            </section>

            <aside className="inspector">
              <div className="tabs">
                <button className={tab === "critique" ? "active" : ""} onClick={() => setTab("critique")}>Critique</button>
                <button className={tab === "references" ? "active" : ""} onClick={() => setTab("references")}>References</button>
                <button className={tab === "revision" ? "active" : ""} onClick={() => setTab("revision")}>Revision</button>
              </div>

              {analysis.result.warning && <div className="demo-notice"><Sparkles size={15} />{analysis.result.warning}</div>}

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
        <p className="upload-privacy">Your artwork is stored for your private browser history and is sent to the configured AI provider only when you request a critique.</p>
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

function IntentConfirmation({ project, draft, value, onChange, busy, onConfirm }: {
  project: Project;
  draft: IntentRestatement;
  value: string;
  onChange: (value: string) => void;
  busy: Busy;
  onConfirm: () => void;
}) {
  return (
    <div className="intent-layout">
      <div className="intent-art"><img src={assetUrl(project.image_url)} alt={project.title} /><div><span>{project.stage}</span><span>{project.style}</span></div></div>
      <section className="intent-card">
        <div className="step-label"><span>1</span> Confirm creative intent</div>
        <p className="eyebrow">Before any critique</p>
        <h2>Let’s make sure we are looking at the same picture.</h2>
        <p className="intent-explainer">The critique will treat this statement as its north star. Edit anything that feels off.</p>
        <label className="intent-editor"><span>ArtMentor’s reading</span><textarea value={value} onChange={(event) => onChange(event.target.value)} rows={6} /></label>
        {draft.assumptions.length > 0 && <div className="assumptions"><span>Assumptions to verify</span>{draft.assumptions.map((item) => <p key={item}><Check size={14} />{item}</p>)}</div>}
        <div className="confirmation-question"><Target size={18} /><p>{draft.confirmation_question}</p></div>
        <button className="primary-action" disabled={busy !== null} onClick={onConfirm}>
          {busy === "analysis" ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
          Confirm and critique <ArrowRight size={17} />
        </button>
        <small className="model-note">
          Intent restated by {draft.provider === "demo" ? "offline demo mode" : draft.provider === "gptsapi" ? `WildAI · ${draft.model}` : draft.model}
        </small>
      </section>
    </div>
  );
}

function LoadingAnalysis() {
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
