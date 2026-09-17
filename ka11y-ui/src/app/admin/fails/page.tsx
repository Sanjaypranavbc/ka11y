"use client";

import { useState } from "react";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { AdminTable, type AdminColumn } from "@/components/admin/AdminTable";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { loadFails } from "@/lib/admin/api";
import type { FailingCriterion } from "@/lib/admin/data";
import { formatNumber } from "@/lib/admin/format";
import { useAdminResource } from "@/lib/admin/useAdminResource";

const WINDOWS = [7, 30, 90, 365] as const;

const SEVERITY_CLASS: Record<string, string> = {
  critical: "bg-adm-failed-bg text-adm-failed",
  serious: "bg-adm-failed-bg text-adm-failed",
  moderate: "bg-adm-review-bg text-adm-review",
  minor: "bg-adm-cancelled-bg text-adm-cancelled",
  unknown: "bg-gray-10 text-gray-80",
};

export default function AdminFailsPage() {
  const { t, lang } = useLanguage();
  const p = t.admin.pages.fails;
  const [days, setDays] = useState<number>(30);
  const { data, status, retry } = useAdminResource(() => loadFails(days), [days]);

  const columns: AdminColumn<FailingCriterion>[] = [
    { key: "criterion", header: p.columns.criterion, render: (f) => <span className="font-medium tabular-nums">{f.criterion}</span> },
    { key: "title", header: p.columns.rule, render: (f) => f.title },
    { key: "level", header: p.columns.level, render: (f) => f.level || "—" },
    {
      key: "severity",
      header: p.columns.severity,
      render: (f) => (
        <span className={`inline-flex rounded-full px-2 py-0.5 text-[12px] font-medium ${SEVERITY_CLASS[f.severity] ?? SEVERITY_CLASS.unknown}`}>
          {f.severity === "unknown" ? p.unknownSeverity : t.admin.severity[f.severity]}
        </span>
      ),
    },
    { key: "occ", header: p.columns.occurrences, align: "right", render: (f) => formatNumber(f.occurrences, lang) },
    { key: "review", header: p.columns.needsReview, align: "right", render: (f) => formatNumber(f.needsReview, lang) },
    { key: "runs", header: p.columns.runs, align: "right", render: (f) => formatNumber(f.runs, lang) },
    { key: "pages", header: p.columns.pages, align: "right", render: (f) => formatNumber(f.pages, lang) },
  ];

  const windowPicker = (
    <fieldset className="flex items-center gap-1 rounded-lg border border-adm-border p-1">
      <legend className="sr-only">{p.windowLabel}</legend>
      {WINDOWS.map((d) => (
        <button
          key={d}
          type="button"
          onClick={() => setDays(d)}
          aria-pressed={days === d}
          className={`min-h-9 rounded-md px-3 text-[13px] font-medium ${days === d ? "bg-brand-green-80 text-white" : "text-gray-80 hover:bg-gray-10"}`}
        >
          {p.days(d)}
        </button>
      ))}
    </fieldset>
  );

  return (
    <>
      <AdminPageHeader title={p.title} subtitle={p.subtitle} />
      <AdminTable
        title={p.tableTitle(days)}
        subtitle={p.tableSubtitle}
        caption={p.caption}
        columns={columns}
        rows={data?.fails ?? []}
        rowKey={(f) => f.criterion}
        status={status}
        onRetry={retry}
        emptyText={p.empty}
        actions={windowPicker}
        minWidth={900}
      />
    </>
  );
}
