export interface AuditViolation {
  rule_id: string;
  wcag_sc: string;
  criterion_name: string;
  level: "A" | "AA" | "AAA";
  severity: "critical" | "high" | "medium" | "low";
  source: "axe" | "python";
  reason: string;
  element_html: string;
  suggested_fix: string;
  help_url?: string;
}

export interface AuditNeedsReview {
  rule_id: string;
  wcag_sc: string;
  criterion_name: string;
  level: "A" | "AA" | "AAA";
  severity: "critical" | "high" | "medium" | "low";
  source: "axe" | "python";
  reason: string;
  element_html: string;
  suggested_fix: string;
  help_url?: string;
}

export interface AuditPass {
  rule_id: string;
  wcag_sc: string;
  criterion_name: string;
  level: "A" | "AA" | "AAA";
  source: "axe" | "python";
  reason: string;
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
}

export interface AuditConfig {
  url: string;
  max_depth: number;
  run_ocr: boolean;
  run_image_audit: boolean;
  run_form_audit: boolean;
  run_label_in_name_audit: boolean;
  run_pause_stop_hide_audit: boolean;
  run_target_size_audit: boolean;
}

export type TabValue = "dashboard" | "violations" | "needs-review" | "passes" | "settings";
