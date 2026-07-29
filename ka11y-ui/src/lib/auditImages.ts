/* ─── Image-visualiser types ───────────────────────────────────────────────
 * Shapes emitted by the Python combined-audit pipeline under
 * result.contrast_report. The image_url is a same-origin path
 * (/api/v1/assets/{id}) proxied to the Python service by next.config rewrites,
 * so <img src={image_url}> loads directly. */

export type ImageClassification =
  | "button"
  | "icon"
  | "logo"
  | "image"
  | "chart"
  | "informative"
  | "decorative"
  | "other";

export interface ContrastDetection {
  text: string;
  confidence: number;
  bbox: number[];
  ratio: number | null;
  AA_passes: boolean | null;
  AAA_passes: boolean | null;
  wcag_violations: string[];
  foreground?: Record<string, unknown> | null;
  background_palette?: unknown[];
  contrast_checks?: unknown[];
}

export interface ContrastImageDetail {
  filename: string;
  path: string;
  image_url: string;
  classification: ImageClassification;
  contrast_violations_count: number;
  detections: ContrastDetection[];
}

export interface ContrastReportSummary {
  total_regions_analysed: number;
  total_violations: number;
  images_with_violations: number;
  pass_rate_pct: number;
}

export interface ContrastReport {
  summary: ContrastReportSummary;
  images: ContrastImageDetail[];
}
