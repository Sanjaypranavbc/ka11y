"use client";

import { Download, FileText } from "lucide-react";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { buildFindingsCsv } from "@/lib/wcagAudit";
import { cn } from "@/lib/utils";

const BUTTON_CLASS =
  "inline-flex items-center gap-1.5 rounded-[8px] border border-brand-green-80 px-3 py-2 text-[14px] text-gray-100 hover:bg-gray-10 sm:px-4 sm:text-[16px]";

/**
 * CSV download is switched off for now (product decision, 2026-09-24): the
 * button stays in place but is always disabled. Flip CSV_DOWNLOAD_ENABLED to
 * bring it back; the export logic below is intact.
 */
const CSV_DOWNLOAD_ENABLED = false;

export function DownloadCsvButton({ className }: { className?: string }) {
  const { auditData } = useAuditData();
  const { t } = useLanguage();
  const handleClick = () => {
    if (!auditData || !CSV_DOWNLOAD_ENABLED) return;
    const blob = new Blob([buildFindingsCsv(auditData)], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "a11y-findings.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={!CSV_DOWNLOAD_ENABLED || !auditData}
      className={cn(BUTTON_CLASS, "disabled:cursor-not-allowed disabled:opacity-50", className)}
    >
      <Download size={15} aria-hidden="true" />
      <span className="hidden sm:inline">{t.downloads.csv}</span>
    </button>
  );
}

export function DownloadPdfButton({ className }: { className?: string }) {
  const { t } = useLanguage();
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className={cn(BUTTON_CLASS, className)}
    >
      <FileText size={15} aria-hidden="true" />
      <span className="hidden sm:inline">{t.downloads.pdf}</span>
    </button>
  );
}
