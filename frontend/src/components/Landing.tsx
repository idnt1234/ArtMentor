import { type ReactNode, useState } from "react";
import { ArrowDown, ArrowRight, ArrowUpRight } from "lucide-react";
import "../landing.css";

type Locale = "en" | "zh-CN";
type Localized = Record<Locale, string>;

interface Study {
  id: string;
  title: Localized;
  artist: Localized;
  medium: Localized;
  intent: Localized;
  date: Localized;
  source: string;
  dimensions: [width: number, height: number];
}

const mayMilton: Study = {
  id: "f02",
  title: { en: "May Milton", "zh-CN": "梅·米尔顿" },
  artist: { en: "Henri de Toulouse-Lautrec", "zh-CN": "亨利·德·图卢兹-洛特雷克" },
  medium: { en: "Color lithograph", "zh-CN": "彩色石版画" },
  intent: {
    en: "Treat this as a finished theatrical poster. I want the sweeping white dress to read first against the flat blue, then lead the eye to her profile and the lettering. Preserve the broad shapes and deliberate distortion.",
    "zh-CN": "把它当作一张完成的剧场海报来点评。我希望观众先在平涂的蓝色背景上看到舒展的白裙，再顺着画面看到人物的侧脸和文字。请保留大块造型和有意的变形。",
  },
  date: { en: "1895", "zh-CN": "1895 年" },
  source: "https://www.clevelandart.org/art/1952.10",
  dimensions: [1152, 1520],
};

const blackSkirt: Study = {
  id: "a01",
  title: { en: "Young Woman with a Black Skirt", "zh-CN": "黑裙少女" },
  artist: { en: "John Singer Sargent", "zh-CN": "约翰·辛格·萨金特" },
  medium: { en: "Watercolor and graphite", "zh-CN": "水彩与石墨" },
  intent: {
    en: "This is a watercolor study of a standing figure. I want the black skirt to establish the silhouette first, then guide the eye to her clasped hands and the small warm areas on her face. Keep the loose brushwork and the unpainted paper.",
    "zh-CN": "这是一幅站姿人物的水彩习作。希望黑裙先稳住人物轮廓，再让视线移向相握的双手和面部的小块暖色。请保留疏松的笔触与纸面留白。",
  },
  date: { en: "Early 1880s", "zh-CN": "1880 年代初" },
  source: "https://www.metmuseum.org/art/collection/search/12478",
  dimensions: [880, 1200],
};

const studies: Study[] = [
  blackSkirt,
  {
    id: "e02",
    title: {
      en: "The Actor Segawa Kikunojo III as a Woman Standing near a Winding Stream",
      "zh-CN": "濑川菊之丞三世女形像",
    },
    artist: { en: "Katsukawa Shunshō", "zh-CN": "胜川春章" },
    medium: { en: "Woodblock print", "zh-CN": "木版画" },
    intent: {
      en: "Study how the fan, sleeve and hem make the actor's gesture readable.",
      "zh-CN": "观察扇子、衣袖与下摆如何让演员的动作清晰可辨。",
    },
    date: { en: "Ca. 1777", "zh-CN": "约 1777 年" },
    source: "https://www.metmuseum.org/art/collection/search/37154",
    dimensions: [576, 1200],
  },
  {
    id: "d04",
    title: { en: "Portrait of Yongzheng Empress", "zh-CN": "雍正皇后像" },
    artist: { en: "Unidentified artist", "zh-CN": "佚名" },
    medium: { en: "Ink and color on silk", "zh-CN": "绢本设色" },
    intent: {
      en: "Study how symmetry and repeated details give the portrait a formal presence.",
      "zh-CN": "观察对称构图与重复纹样如何营造宫廷肖像的庄重感。",
    },
    date: { en: "19th century", "zh-CN": "19 世纪" },
    source: "https://www.metmuseum.org/art/collection/search/53528",
    dimensions: [787, 1250],
  },
  {
    id: "b01",
    title: { en: "Three Dancers Preparing for Class", "zh-CN": "三位舞者准备上课" },
    artist: { en: "Edgar Degas", "zh-CN": "埃德加·德加" },
    medium: { en: "Pastel on paper", "zh-CN": "纸本粉彩" },
    intent: {
      en: "Study how overlapping bodies and changes in silhouette separate three figures in a tight composition.",
      "zh-CN": "观察在紧凑构图中，人物的相互遮挡与轮廓变化如何让三位舞者各自清晰可辨。",
    },
    date: { en: "After 1878", "zh-CN": "1878 年后" },
    source: "https://www.metmuseum.org/art/collection/search/436163",
    dimensions: [1050, 1100],
  },
  {
    id: "c02",
    title: {
      en: "Portrait of a Young Woman Wearing a Cloak and Bonnet",
      "zh-CN": "披斗篷戴帽的年轻女子",
    },
    artist: { en: "Théodore Chassériau", "zh-CN": "泰奥多尔·夏塞里奥" },
    medium: { en: "Graphite", "zh-CN": "石墨素描" },
    intent: {
      en: "Study how line weight and the shape of the cloak frame the face.",
      "zh-CN": "观察线条轻重与斗篷的形状如何将视线引向面部。",
    },
    date: { en: "1850", "zh-CN": "1850 年" },
    source: "https://www.metmuseum.org/art/collection/search/409006",
    dimensions: [854, 1100],
  },
  mayMilton,
  {
    id: "f03",
    title: { en: "Divan Japonais", "zh-CN": "日本咖啡馆" },
    artist: { en: "Henri de Toulouse-Lautrec", "zh-CN": "亨利·德·图卢兹-洛特雷克" },
    medium: { en: "Color lithograph", "zh-CN": "彩色石版画" },
    intent: {
      en: "Study how figure placement and large areas of black set a visual hierarchy for this poster.",
      "zh-CN": "观察人物的位置与大块黑色如何建立海报的视觉主次。",
    },
    date: { en: "1892–93", "zh-CN": "1892–1893 年" },
    source: "https://www.metmuseum.org/art/collection/search/334197",
    dimensions: [908, 1200],
  },
];

interface CaseCapture {
  file: string;
  title: string;
  description: string;
  dimensions: [width: number, height: number];
}

const caseStudies: Record<Locale, { artwork: Study; captures: CaseCapture[] }> = {
  en: {
    artwork: mayMilton,
    captures: [
      {
        file: "case-intent.webp",
        title: "Confirm intent",
        description: "Before the critique, ArtMentor lists what it sees and asks the artist to confirm its reading of the study goal.",
        dimensions: [1188, 1668],
      },
      {
        file: "case-critique.webp",
        title: "Annotated critique",
        description: "Three numbered regions locate the suggested changes. The side panel summarizes composition, value, color, and narrative.",
        dimensions: [1188, 968],
      },
      {
        file: "case-priorities.webp",
        title: "Revision priorities",
        description: "The first priority suggests opening small gaps between the lettering and the hair so each shape reads clearly.",
        dimensions: [1188, 968],
      },
    ],
  },
  "zh-CN": {
    artwork: blackSkirt,
    captures: [
      {
        file: "case-zh-intent.webp",
        title: "确认意图",
        description: "点评开始前，ArtMentor 列出画面中可见的事实，并请创作者确认它对研习目标的理解。",
        dimensions: [1188, 1590],
      },
      {
        file: "case-zh-critique.webp",
        title: "标注与点评",
        description: "三个编号区域指出建议修改的位置。侧栏概括了构图、明暗、色彩和视觉叙事的反馈。",
        dimensions: [1188, 968],
      },
      {
        file: "case-zh-priorities.webp",
        title: "修改优先级",
        description: "第一条建议是把双手、手后阴影和上衣亮面分清，让相握的双手从衣服中显出来。",
        dimensions: [1188, 968],
      },
    ],
  },
};

const copy = {
  en: {
    heroLabel: "Art critique for illustrators",
    heroFirst: "Make your next",
    heroSecond: "revision count.",
    heroDescription: "Get feedback on composition, value, color, and visual storytelling, starting with what you want the viewer to notice or feel.",
    uploadAction: "Upload artwork",
    caseAction: "See the workflow",
    uploadTitle: "Start a critique",
    uploadDescription: "Add your artwork and tell ArtMentor what you’re working toward.",
    caseTitle: "From artwork to critique",
    caseDescription: "Follow a critique of May Milton from the study goal to annotated feedback and revision priorities.",
    original: "Original artwork",
    caseIntent: "Study prompt",
    caseViews: "Critique walkthrough",
    openCapture: "View full size",
    howTitle: "How it works",
    steps: [
      ["Upload your artwork", "Start with a sketch, color rough, or finished illustration. Choose the stage you’re working in."],
      ["Confirm your intent", "Describe what you want people to see or feel. Check ArtMentor’s restatement before starting the critique."],
      ["Revise and compare", "Work through the highest-priority feedback, then upload an update to see what changed."],
    ],
    galleryTitle: "Public-domain studies",
    galleryDescription: "Load a museum artwork and a suggested study prompt. You can edit the prompt before requesting feedback.",
    loadStudy: "Load this study",
    finalTitle: "What are you working on?",
    met: "The Met",
    cma: "Cleveland Museum of Art",
  },
  "zh-CN": {
    heroLabel: "面向插画创作者的作品点评",
    heroFirst: "下一次修改，",
    heroSecond: "从这里开始。",
    heroDescription: "先说说你希望观众看到什么、感受到什么，再获得关于构图、明暗、色彩与视觉叙事的反馈。",
    uploadAction: "上传作品",
    caseAction: "查看点评流程",
    uploadTitle: "开始点评",
    uploadDescription: "上传作品，告诉 ArtMentor 你在这张画里想实现什么。",
    caseTitle: "从原作到点评",
    caseDescription: "以《黑裙少女》为例，看看点评如何从确认研习目标走到画面标注和修改建议。",
    original: "原作",
    caseIntent: "研习目标",
    caseViews: "点评流程",
    openCapture: "查看大图",
    howTitle: "使用步骤",
    steps: [
      ["上传作品", "可以从草稿、配色稿或完成的插画开始，选择你当前所处的创作阶段。"],
      ["确认创作意图", "说明你希望观众看到什么、感受到什么。开始点评前，先确认 ArtMentor 对你意图的理解。"],
      ["修改并对比", "先尝试最值得处理的修改建议，再上传新版本，看看画面有什么变化。"],
    ],
    galleryTitle: "公共领域作品研习",
    galleryDescription: "载入博物馆藏品和一条研习提示，提交点评前可以按自己的目标修改提示。",
    loadStudy: "载入这张作品",
    finalTitle: "最近在画什么？",
    met: "大都会艺术博物馆",
    cma: "克利夫兰艺术博物馆",
  },
} as const;

const showcase = `${import.meta.env.BASE_URL}showcase/`;
const imageUrl = (study: Study) => `${showcase}${study.id}.webp`;

function StudyImage({ study, locale, hero = false }: { study: Study; locale: Locale; hero?: boolean }) {
  const [width, height] = study.dimensions;
  return (
    <img
      src={imageUrl(study)}
      alt={study.title[locale]}
      width={width}
      height={height}
      loading={hero ? "eager" : "lazy"}
      fetchPriority={hero ? "high" : "auto"}
      decoding="async"
    />
  );
}

function UploadLink({ label }: { label: string }) {
  return (
    <a className="landing-button" href="#upload">
      {label}<ArrowUpRight size={19} aria-hidden="true" />
    </a>
  );
}

export default function Landing({ children, locale, onTryStudy, busy }: {
  children: ReactNode;
  locale: Locale;
  onTryStudy: (url: string, title: string, style: string, intent: string) => Promise<void>;
  busy: boolean;
}) {
  const text = copy[locale];
  const [captureIndex, setCaptureIndex] = useState(1);
  const { artwork, captures } = caseStudies[locale];
  const capture = captures[captureIndex];
  const captureUrl = `${showcase}${capture.file}`;
  const museum = (study: Study) => study.id === mayMilton.id ? text.cma : text.met;
  const loadStudy = (study: Study) => onTryStudy(imageUrl(study), study.title[locale], study.medium[locale], study.intent[locale]);

  return (
    <div className="landing" lang={locale}>
      <section className="landing-frame landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero-copy">
          <p className="landing-kicker">{text.heroLabel}</p>
          <h1 id="landing-title">
            <span>{text.heroFirst}</span>{" "}
            <em>{text.heroSecond}</em>
          </h1>
          <p className="landing-hero-description">{text.heroDescription}</p>
          <div className="landing-hero-actions">
            <UploadLink label={text.uploadAction} />
            <a className="landing-inline-link" href="#case-study">{text.caseAction}<ArrowDown size={16} aria-hidden="true" /></a>
          </div>
        </div>
        <figure className="landing-hero-figure">
          <div className="landing-hero-art">
            <StudyImage study={mayMilton} locale={locale} hero />
          </div>
          <figcaption>
            <span><cite>{mayMilton.title[locale]}</cite> · {mayMilton.date[locale]}</span>
            <a href={mayMilton.source} aria-label={text.cma}><ArrowUpRight size={17} aria-hidden="true" /></a>
          </figcaption>
        </figure>
      </section>

      <section className="landing-section landing-upload" id="upload" aria-labelledby="landing-upload-title">
        <div className="landing-frame">
          <header className="landing-section-header">
            <h2 id="landing-upload-title">{text.uploadTitle}</h2>
            <p>{text.uploadDescription}</p>
          </header>
          <div className="landing-upload-form">{children}</div>
        </div>
      </section>

      <section className="landing-section landing-case" id="case-study" aria-labelledby="landing-case-title">
        <div className="landing-frame">
          <header className="landing-section-header">
            <h2 id="landing-case-title">{text.caseTitle}</h2>
            <p>{text.caseDescription}</p>
          </header>
          <div className="landing-case-grid">
            <div className="landing-case-context">
              <figure className="landing-case-original">
                <div className="landing-case-image"><StudyImage study={artwork} locale={locale} /></div>
                <figcaption>
                  <p className="landing-kicker">{text.original}</p>
                  <a href={artwork.source}>{artwork.title[locale]} <ArrowUpRight size={16} aria-hidden="true" /></a>
                  <p>{artwork.artist[locale]} · {artwork.date[locale]}</p>
                </figcaption>
              </figure>
              <div className="landing-case-prompt">
                <p className="landing-kicker">{text.caseIntent}</p>
                <p>{artwork.intent[locale]}</p>
              </div>
              <button className="landing-inline-link" type="button" disabled={busy} onClick={() => void loadStudy(artwork)}>
                {text.loadStudy}<ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
            <div className="landing-case-captures">
              <div className="landing-case-picker" role="group" aria-label={text.caseViews}>
                {captures.map((item, index) => (
                  <button key={item.file} type="button" aria-pressed={index === captureIndex} aria-controls="landing-case-capture" onClick={() => setCaptureIndex(index)}>
                    {item.title}
                  </button>
                ))}
              </div>
              <figure id="landing-case-capture">
                <div className="landing-case-preview">
                  <img src={captureUrl} alt={capture.title} width={capture.dimensions[0]} height={capture.dimensions[1]} loading="lazy" decoding="async" />
                </div>
                <figcaption>
                  <p aria-live="polite">{capture.description}</p>
                  <a href={captureUrl} target="_blank" rel="noreferrer">{text.openCapture} <ArrowUpRight size={15} aria-hidden="true" /></a>
                </figcaption>
              </figure>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section" id="how-it-works" aria-labelledby="landing-how-title">
        <div className="landing-frame">
          <header className="landing-section-header">
            <h2 id="landing-how-title">{text.howTitle}</h2>
          </header>
          <ol className="landing-steps" role="list">
            {text.steps.map(([title, description], index) => (
              <li key={title}>
                <span className="landing-step-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <h3>{title}</h3>
                <p>{description}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="landing-section landing-gallery" id="gallery" aria-labelledby="landing-gallery-title">
        <div className="landing-frame">
          <header className="landing-section-header">
            <h2 id="landing-gallery-title">{text.galleryTitle}</h2>
            <p>{text.galleryDescription}</p>
          </header>
          <ul className="landing-studies" role="list">
            {studies.map((study) => (
              <li className="landing-study" key={study.id}>
                <div className="landing-study-image"><StudyImage study={study} locale={locale} /></div>
                <div className="landing-study-copy">
                  <p className="landing-kicker">{study.medium[locale]}</p>
                  <h3>{study.title[locale]}</h3>
                  <p>{study.artist[locale]} · {study.date[locale]}</p>
                  <a className="landing-source" href={study.source}>{museum(study)} · CC0 <ArrowUpRight size={13} aria-hidden="true" /></a>
                </div>
                <button
                  className="landing-study-button"
                  type="button"
                  disabled={busy}
                  aria-label={`${text.loadStudy} · ${study.title[locale]}`}
                  onClick={() => void loadStudy(study)}
                >
                  {text.loadStudy}<ArrowRight size={16} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="landing-section landing-final" aria-labelledby="landing-final-title">
        <div className="landing-frame">
          <h2 id="landing-final-title">{text.finalTitle}</h2>
          <UploadLink label={text.uploadAction} />
        </div>
      </section>
    </div>
  );
}
