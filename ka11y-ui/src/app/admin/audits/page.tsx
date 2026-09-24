"use client";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { useAdminConsole } from "@/components/admin/AdminShell";
import { AdminTable, type AdminColumn } from "@/components/admin/AdminTable";
import { StatusPill } from "@/components/admin/StatusPill";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { loadAudits } from "@/lib/admin/api";
import type { AuditJob } from "@/lib/admin/data";
import { formatDateTime, formatNumber } from "@/lib/admin/format";
import { useAdminResource } from "@/lib/admin/useAdminResource";

const HISTORY_LIMIT = 200;

/** Audit history: one row per run, newest first. Internal job ids are never shown. */
export default function AdminAuditsPage() {
  const { t, lang } = useLanguage();
  const p = t.admin.pages.audits;
  const { openAudit } = useAdminConsole();
  const { data, status, retry } = useAdminResource(() => loadAudits({ limit: HISTORY_LIMIT }));

  const columns: AdminColumn<AuditJob>[] = [
    {
      key: "ranAt",
      header: p.columns.ranAt,
      render: (j) => {
        const at = j.startedAt ?? j.createdAt;
        return (
          <time dateTime={at} className="whitespace-nowrap">
            {formatDateTime(at, lang)}
          </time>
        );
      },
    },
    {
      key: "page",
      header: p.columns.page,
      render: (j) => (
        <button
          type="button"
          onClick={() => openAudit(j)}
          aria-label={p.openDetails(j.targetUrl)}
          className="-mx-2 inline-flex min-h-11 max-w-[420px] items-center rounded-md px-2 text-left font-medium text-brand-green-80 underline decoration-brand-green-80/40 underline-offset-4 hover:decoration-brand-green-80"
        >
          <span className="break-all">{j.targetUrl}</span>
        </button>
      ),
    },
    { key: "status", header: p.columns.status, render: (j) => <StatusPill status={j.status} /> },
    { key: "fails", header: p.columns.fails, align: "right", render: (j) => formatNumber(j.fails, lang) },
    { key: "passes", header: p.columns.passes, align: "right", render: (j) => formatNumber(j.passed, lang) },
    { key: "review", header: p.columns.needsReview, align: "right", render: (j) => formatNumber(j.needsReview, lang) },
  ];

  const rows = data?.jobs ?? [];

  return (
    <>
      <AdminPageHeader title={p.title} subtitle={p.subtitle} />
      <AdminTable
        title={p.tableTitle(rows.length)}
        caption={p.caption}
        columns={columns}
        rows={rows}
        rowKey={(j) => j.id}
        status={status}
        onRetry={retry}
        emptyText={p.empty}
        minWidth={880}
      />
    </>
  );
}
