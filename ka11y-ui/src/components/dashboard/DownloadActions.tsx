"use client";

import { Download, FileText } from "lucide-react";
import { pageFindings } from "@/lib/dashboardData";
import { cn } from "@/lib/utils";

const BUTTON_CLASS =
  "inline-flex items-center gap-1.5 rounded-[8px] border border-brand-green-80 px-3 py-2 text-[14px] text-gray-100 hover:bg-gray-10 sm:px-4 sm:text-[16px]";

function buildFindingsCsv(): string {
  const headers = ["Page Name", "URL", "Score", "Findings", "Violations", "Needs Review", "Passes"];
  const rows = pageFindings.map((row) => [
    row.pageName,
    row.url,
    `${row.score}%`,
    row.findings,
    row.violations,
    row.needsReview,
    row.passes,
  ]);
  return [headers, ...rows].map((line) => line.join(",")).join("\n");
}

export function DownloadCsvButton({ className }: { className?: string }) {
  const handleClick = () => {
    const blob = new Blob([buildFindingsCsv()], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "a11y-findings.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <button type="button" onClick={handleClick} className={cn(BUTTON_CLASS, className)}>
      <Download size={15} aria-hidden="true" />
      <span className="hidden sm:inline">Download CSV</span>
    </button>
  );
}

export function DownloadPdfButton({ className }: { className?: string }) {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className={cn(BUTTON_CLASS, className)}
    >
      <FileText size={15} aria-hidden="true" />
      <span className="hidden sm:inline">Download PDF</span>
    </button>
  );
}
