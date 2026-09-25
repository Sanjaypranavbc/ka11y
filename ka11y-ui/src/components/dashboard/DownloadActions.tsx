"use client";

import { ExportMenu } from "@/components/admin/ExportMenu";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { REPORT_EXPORT_FORMATS, reportExportHref } from "@/lib/reportExport";

/**
 * Report export is switched off for now (product decision, 2026-09-25): the
 * button stays in place but is always disabled. Flip REPORT_EXPORT_ENABLED to
 * bring it back; the menu, the links and the backend endpoint
 * (GET /api/v1/combined/{jobId}/export) are all intact.
 */
const REPORT_EXPORT_ENABLED = false;

/**
 * "Export report" menu for the dashboard header: JSON / CSV / HTML / PDF links
 * to the backend export endpoint (see lib/reportExport.ts). Replaces the
 * former client-side CSV build and window.print() PDF (2026-09-25): the
 * files are generated server-side from the stored report, so the browser
 * holds nothing the dashboard payload does not already show.
 *
 * When enabled, it is still disabled until an audit with a known job id is
 * loaded (a result restored from an older session may lack one).
 */
export function DownloadReportMenu({ className }: { className?: string }) {
  const { auditData, jobId } = useAuditData();
  const { t } = useLanguage();
  const subject = auditData?.url ?? "";
  return (
    <ExportMenu
      jobId={jobId ?? ""}
      subject={subject}
      formats={REPORT_EXPORT_FORMATS}
      hrefFor={reportExportHref}
      labels={t.downloads}
      disabled={!REPORT_EXPORT_ENABLED || !auditData || !jobId}
      className={className}
    />
  );
}
