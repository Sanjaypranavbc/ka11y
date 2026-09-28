"use client";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { AdminTable, type AdminColumn } from "@/components/admin/AdminTable";
import { ExportMenu } from "@/components/admin/ExportMenu";
import { StatusPill } from "@/components/admin/StatusPill";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { loadAudits } from "@/lib/admin/api";
import type { AuditJob } from "@/lib/admin/data";
import { formatDateTime, formatNumber } from "@/lib/admin/format";
import { useAdminResource } from "@/lib/admin/useAdminResource";

const LIMIT = 200;

/**
 * Reports: every audit run with an Export menu (CSV / PDF / HTML). The file
 * is built by the API from the stored report, so only completed runs can be
 * exported; other rows say why.
 */
export default function AdminReportsPage() {
  const { t, lang } = useLanguage();
  const p = t.admin.pages.reports;
  const { data, status, retry } = useAdminResource(() => loadAudits({ limit: LIMIT }));

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
      render: (j) => <span className="inline-block max-w-[420px] break-all">{j.targetUrl}</span>,
    },
    { key: "status", header: p.columns.status, render: (j) => <StatusPill status={j.status} /> },
    { key: "pages", header: p.columns.pages, align: "right", render: (j) => formatNumber(j.pages, lang) },
    {
      key: "export",
      header: p.columns.export,
      render: (j) =>
        j.status === "completed" ? (
          <ExportMenu jobId={j.id} subject={j.targetUrl} />
        ) : (
          <span className="text-[13px] text-gray-80">{p.notExportable}</span>
        ),
    },
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
        minWidth={820}
      />
    </>
  );
}
