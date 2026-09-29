import type { ExportFormat } from "@/lib/admin/data";

/** Formats the dashboard's "Export report" menu offers, in menu order. */
export const REPORT_EXPORT_FORMATS: readonly ExportFormat[] = ["json", "csv", "html", "pdf"];

/**
 * Download link for the full audit report. The file is generated and streamed
 * by the Python service (`GET /api/v1/combined/{jobId}/export`), proxied
 * same-origin by next.config.ts so the session cookie travels with it. The
 * browser never sees the report data the file is built from: the export
 * carries WCAG technique/situation tags for every finding, which the
 * dashboard's own payload deliberately omits for failures.
 */
export const reportExportHref = (jobId: string, format: ExportFormat) =>
  `/api/v1/combined/${encodeURIComponent(jobId)}/export?format=${format}`;
