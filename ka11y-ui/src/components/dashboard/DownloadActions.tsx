"use client";

import { ExportMenu } from "@/components/admin/ExportMenu";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { REPORT_EXPORT_FORMATS, reportExportHref } from "@/lib/reportExport";

/**
 * "Export report" menu for the dashboard header: Summary (HTML) / CSV / PDF
 * links to the backend export endpoint (see lib/reportExport.ts). Every
 * format carries the WCAG technique and situation tags for each finding,
 * which the dashboard payload itself omits for failures. The files are
 * generated server-side from the stored report (2026-09-25), so the browser
 * holds nothing the dashboard does not already show.
 *
 * Re-enabled 2026-10-01 (it had been switched off since 2026-09-25). The
 * button stays disabled until an audit with a known job id is loaded (a
 * result restored from an older session may lack one).
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
      disabled={!auditData || !jobId}
      className={className}
    />
  );
}
