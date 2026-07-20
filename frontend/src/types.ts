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
