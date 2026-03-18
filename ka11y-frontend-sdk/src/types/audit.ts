export interface AuditViolation {
  rule_id: string;
  wcag_sc: string | null;
  criterion_name: string | null;
  level: "A" | "AA" | "AAA" | null;
  severity: "critical" | "high" | "medium" | "low" | null;
  source: "axe" | "python";
  reason: string;
  element_html: string;
  suggested_fix: string | null;
  help_url?: string | null;
}

export interface AuditNeedsReview {
  rule_id: string;
  wcag_sc: string | null;
  criterion_name: string | null;
  level: "A" | "AA" | "AAA" | null;
  severity: "critical" | "high" | "medium" | "low" | null;
  source: "axe" | "python";
  reason: string;
  element_html: string;
  suggested_fix: string | null;
  help_url?: string | null;
}

export interface ContrastDetection {
  text: string;
  confidence: number;
  bbox: number[];
  ratio: number | null;
  AA_normal: boolean | null;
  AA_large: boolean | null;
  AAA_normal: boolean | null;
  AAA_large: boolean | null;
  wcag_violations: string[];
}

export interface ContrastImageDetail {
  filename: string;
  path: string;
  image_url: string;          // injected by backend: /api/v1/combined/{job_id}/image?path=...
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

export interface AuditPass {
  rule_id: string;
  wcag_sc: string;
  criterion_name: string;
  level: "A" | "AA" | "AAA";
  source: "axe" | "python";
  reason: string;
}

export interface StageInfo {
  name: string;
  status: "running" | "completed" | "error";
  started_at: string;
  completed_at?: string;
  findings_count?: number;
  error?: string;
}

export interface AuditResult {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  url: string;
  generated_at: string;
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
}

export interface AuditConfig {
  url: string;
  max_depth: number;
  wcag_level: "A" | "AA" | "AAA";
  run_ocr: boolean;
  run_image_audit: boolean;
  run_form_audit: boolean;
  run_label_in_name_audit: boolean;
  run_pause_stop_hide_audit: boolean;
  run_target_size_audit: boolean;
}

export type TabValue = "dashboard" | "violations" | "needs-review" | "passes" | "image-visualisation" | "settings";