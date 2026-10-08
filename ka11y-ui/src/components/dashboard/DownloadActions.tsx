"use client";

import { ExportMenu } from "@/components/admin/ExportMenu";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { useRunningAudit } from "@/components/dashboard/RunningAuditContext";
import { isActive } from "@/lib/runningAudit";
import { REPORT_EXPORT_FORMATS, reportExportHref } from "@/lib/reportExport";

/**
 * "Export report" menu for the dashboard header: JSON / CSV / HTML / PDF links
 * to the backend export endpoint (see lib/reportExport.ts). Replaces the
 * former client-side CSV build and window.print() PDF (2026-09-25): the
 * files are generated server-side from the stored report, so the browser
 * holds nothing the dashboard payload does not already show.
 *
 * Enabled once an audit has completed: it needs a loaded result with a known
 * job id (a result restored from an older session may lack one), and it stays
 * inert while a new audit is queued or running, so the previous audit's report
 * cannot be exported under the new target's header (re-enabled 2026-10-08).
 */
export function DownloadReportMenu({ className }: { className?: string }) {
  const { auditData, jobId } = useAuditData();
  const { running } = useRunningAudit();
  const { t } = useLanguage();
  const subject = auditData?.url ?? "";
  const auditInProgress = running !== null && isActive(running.status);
  return (
    <ExportMenu
      jobId={jobId ?? ""}
      subject={subject}
      formats={REPORT_EXPORT_FORMATS}
      hrefFor={reportExportHref}
      labels={t.downloads}
      disabled={!auditData || !jobId || auditInProgress}
      className={className}
    />
  );
}
