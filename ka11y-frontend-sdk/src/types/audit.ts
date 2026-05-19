export type AuditSource = "axe" | "python" | "custom" | "unknown" | (string & {});

interface AuditElementInfo {
  element_html: string;
  element_tag?: string | null;
  element_id?: string | null;
  element_selector?: string | null;
  image_reference?: string | null;
  image_src?: string | null;
  image_text?: string | null;
}

export interface AuditViolation extends AuditElementInfo {
  rule_id: string;
  wcag_sc: string | null;
  criterion_name: string | null;
  level: "A" | "AA" | "AAA" | null;
  severity: "critical" | "high" | "medium" | "low" | null;
  source: AuditSource;
  reason: string;
  suggested_fix: string | null;
  help_url?: string | null;
}

export interface AuditNeedsReview extends AuditElementInfo {
  rule_id: string;
  wcag_sc: string | null;
  criterion_name: string | null;
  level: "A" | "AA" | "AAA" | null;
  severity: "critical" | "high" | "medium" | "low" | null;
  source: AuditSource;
  reason: string;
  suggested_fix: string | null;
  help_url?: string | null;
}

export interface ContrastDetection {
  text: string;
  confidence: number;
  bbox: number[];
  ratio: number | null;
  /** Backend field: overall AA compliance (normal + large text combined) */
  AA_passes: boolean | null;
  /** Backend field: overall AAA compliance */
  AAA_passes: boolean | null;
  wcag_violations: string[];
  // Extra fields returned by the backend but not rendered directly
  foreground?: Record<string, unknown> | null;
  background_palette?: unknown[];
  contrast_checks?: unknown[];
}

export type ImageClassification =
  | "button" | "icon" | "logo" | "image" | "chart"
  | "informative" | "decorative" | "other";

export interface ContrastImageDetail {
  filename: string;
  path: string;
  image_url: string;          // injected by backend: /api/v1/combined/{job_id}/image?path=...
  classification: ImageClassification; // derived from storage path by backend
  contrast_violations_count: number;
  detections: ContrastDetection[];
}

export interface ContrastReport {
  summary: {
    total_regions_analysed: number;
    total_violations: number;
    images_with_violations: number;
    pass_rate_pct: number;
  };
  table: Record<string, unknown>[];
  images: ContrastImageDetail[];
}

export interface ImageAuditImageDetail {
  filename: string;
  path: string;
  image_url: string;
  src?: string | null;
  url?: string | null;
  alt_text?: string | null;
  title?: string | null;
  classification: ImageClassification;
  sub_type?: string | null;
  overall_status: "PASSED" | "FAILED" | string;
  has_ocr_text: boolean;
  detected_text: string;
  contrast_violations_count: number;
  wcag_1_1_1_status: string;
  wcag_4_1_2_status: string;
  wcag_1_4_5_status: string;
  wcag_1_4_11_status: string;
  wcag_1_1_1_reason: string;
  wcag_4_1_2_reason: string;
  wcag_1_4_5_reason: string;
  wcag_1_4_11_reason: string;
}

export interface ImageAuditReport {
  summary: {
    total_images: number;
    passed: number;
    failed: number;
    with_ocr_text: number;
    with_contrast_violations: number;
    by_classification: Record<string, { passed: number; failed: number; total: number }>;
  };
  images: ImageAuditImageDetail[];
}

export interface AuditPass extends AuditElementInfo {
  rule_id: string;
  wcag_sc: string | null;
  criterion_name: string | null;
  level: "A" | "AA" | "AAA" | null;
  source: AuditSource;
  reason: string;
  help_url?: string | null;
}

export interface StageInfo {
  name: string;
  status: "running" | "completed" | "error";
  started_at: string;
  completed_at?: string;
  findings_count?: number;
  error?: string;
  index?: number;
  total?: number;
  weight?: number;
}

export interface JobPlanStage {
  key: string;
  weight: number;
}

export interface JobPlan {
  stages: JobPlanStage[];
  total: number;
  weight_total: number;
  started_at: string;
}

export interface StageProgressInfo {
  stage_name: string;
  current: number;
  total: number;
  phase?: string;
}

export interface JobFailure {
  error: string;
  stage?: string;
  location?: string;
  traceback?: string;
}

export interface AuditResult {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  url: string;
  generated_at: string;
  lang?: string;
  total: number;
  violations_count: number;
  needs_review_count: number;
  passes_count: number;
  violations: AuditViolation[];
  needs_review: AuditNeedsReview[];
  passes: AuditPass[];
  error?: string;
  warnings?: string[];
  current_stage?: string | null;
  stages?: StageInfo[];
  contrast_report?: ContrastReport | null;
  image_audit_report?: ImageAuditReport | null;
}

export interface AuditConfig {
  url: string;
  max_depth: number;
  wcag_level: "A" | "AA" | "AAA";
  lang: "auto" | "en" | "ja";
  run_ocr: boolean;
  run_image_audit: boolean;
  run_form_audit: boolean;
  run_label_in_name_audit: boolean;
  run_pause_stop_hide_audit: boolean;
  run_target_size_audit: boolean;
  run_media_audit: boolean;
  run_sensory_audit: boolean;
  // Rendered-layout checks (Playwright)
  run_resize_text_audit: boolean;
  run_reflow_audit: boolean;
  run_text_spacing_audit: boolean;
  run_orientation_audit: boolean;
  run_hover_focus_content_audit: boolean;
  run_focus_not_obscured_min_audit: boolean;
  run_focus_not_obscured_enh_audit: boolean;
}

export type TabValue = "dashboard" | "violations" | "needs-review" | "passes" | "image-visualisation" | "wcag-rules" | "settings";
