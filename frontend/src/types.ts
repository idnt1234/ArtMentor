export type DimensionName = "composition" | "value" | "color" | "narrative";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Project {
  id: string;
  title: string;
  image_url: string;
  stage: string;
  style: string;
  intent_original: string;
  intent_confirmed?: string | null;
  latest_analysis_id?: string | null;
  created_at: string;
}

export interface IntentRestatement {
  restatement: string;
  assumptions: string[];
  confirmation_question: string;
  visual_observations: string[];
  action_status: "clear" | "ambiguous" | "unknown" | "not_applicable";
  action_hypotheses: Array<{
    label: string;
    visible_evidence: string;
  }>;
  action_question?: string | null;
  stage_assessment: "consistent" | "uncertain" | "mismatch";
  suggested_stage?: string | null;
  stage_note: string;
  provider: string;
  model: string;
}

export interface DimensionAnalysis {
  dimension: DimensionName;
  score: number;
  headline: string;
  observations: string[];
}

export interface Suggestion {
  id: string;
  dimension: DimensionName;
  title: string;
  technical_term: string;
  plain_explanation: string;
  goal: string;
  steps: string[];
  priority: "high" | "medium" | "low";
  region: Rect;
}

export interface ReferenceItem {
  id: string;
  title: string;
  artist: string;
  date: string;
  image_url: string;
  source_url: string;
  license: string;
  license_url: string;
  rationale: string;
}

export interface VisualMetrics {
  width: number;
  height: number;
  mean_value: number;
  value_contrast: number;
  dark_ratio: number;
  light_ratio: number;
  mean_saturation: number;
  colorfulness: number;
  edge_density: number;
  focal_point_x: number;
  focal_point_y: number;
  thirds_distance: number;
  palette: string[];
}

export interface CritiqueResult {
  intent_restatement: string;
  overall_read: string;
  strengths: string[];
  dimensions: DimensionAnalysis[];
  suggestions: Suggestion[];
  exercise: {
    title: string;
    duration_minutes: number;
    instructions: string[];
    success_signal: string;
  };
  references: ReferenceItem[];
  visual_metrics: VisualMetrics;
  provider: string;
  model: string;
  warning?: string | null;
  confirmed_stage?: string;
  confirmed_action?: string | null;
}

export interface Analysis {
  id: string;
  project_id: string;
  result: CritiqueResult;
  created_at: string;
}

export interface SampleArtwork {
  id: string;
  title: string;
  artist: string;
  date: string;
  image_url: string;
  source_url: string;
  license: string;
  default_intent: string;
  default_style: string;
}

export interface ComparisonResult {
  summary: string;
  changes: Array<{
    dimension: DimensionName;
    outcome: "improved" | "unchanged" | "tradeoff" | "uncertain";
    explanation: string;
    evidence: string;
  }>;
  next_step: string;
  before_metrics: VisualMetrics;
  after_metrics: VisualMetrics;
  provider: string;
  model: string;
  warning?: string | null;
}

export interface Revision {
  id: string;
  project_id: string;
  image_url: string;
  comparison: ComparisonResult;
  created_at: string;
}

export type PoseStyleMode = "realistic" | "semi_realistic" | "stylized" | "intentional_distortion";
export type PoseStatus = "created" | "estimated" | "confirmed" | "compared";

export interface PoseKeypoint {
  name: string;
  x: number;
  y: number;
  confidence: number;
  source: "model" | "user";
  visibility: "predicted" | "visible" | "hidden" | "unknown";
}

export interface PoseSkeleton {
  bbox: Rect;
  keypoints: PoseKeypoint[];
  confirmed: boolean;
  warnings: string[];
  model: string;
}

export interface PoseFinding {
  status: "consistent" | "suspicious" | "insufficient";
  category: "position" | "proportion" | "angle" | "alignment" | "evidence";
  title: string;
  observation: string;
  reference: string;
  difference: string;
  keypoints: string[];
  confidence: number;
  suggestion: string;
}

export interface PoseCheckResult {
  overall_status: "consistent" | "suspicious" | "insufficient";
  assumptions: string[];
  findings: PoseFinding[];
  comparable_keypoint_count: number;
  tolerance_mode: PoseStyleMode;
}

export interface PoseComparison {
  id: string;
  project_id: string;
  artwork_image_url: string;
  reference_image_url: string;
  reference_filename: string;
  style_mode: PoseStyleMode;
  status: PoseStatus;
  artwork_skeleton?: PoseSkeleton | null;
  reference_skeleton?: PoseSkeleton | null;
  result?: PoseCheckResult | null;
  created_at: string;
  updated_at: string;
}

export interface PoseInspection {
  id: string;
  project_id: string;
  artwork_image_url: string;
  style_mode: PoseStyleMode;
  status: "estimated" | "confirmed" | "checked";
  skeleton: PoseSkeleton;
  result?: PoseCheckResult | null;
  created_at: string;
  updated_at: string;
}
