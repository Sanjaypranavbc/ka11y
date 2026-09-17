"use client";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { AdminTable, type AdminColumn } from "@/components/admin/AdminTable";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { loadSystemEvents } from "@/lib/admin/api";
import type { SystemEvent } from "@/lib/admin/data";
import { formatDateTime } from "@/lib/admin/format";
import { useAdminResource } from "@/lib/admin/useAdminResource";

const LEVEL_CLASS: Record<SystemEvent["level"], string> = {
  info: "bg-adm-completed-bg text-adm-completed",
  warn: "bg-adm-review-bg text-adm-review",
  error: "bg-adm-failed-bg text-adm-failed",
};

export default function AdminSystemEventsPage() {
  const { t, lang } = useLanguage();
  const p = t.admin.pages.systemEvents;
  const { data, status, retry } = useAdminResource(loadSystemEvents);

  const columns: AdminColumn<SystemEvent>[] = [
    { key: "at", header: p.columns.time, render: (e) => <time dateTime={e.at}>{formatDateTime(e.at, lang)}</time> },
    {
      key: "level",
      header: p.columns.level,
      render: (e) => (
        <span className={`inline-flex rounded-full px-2 py-0.5 text-[12px] font-medium ${LEVEL_CLASS[e.level]}`}>
          {t.admin.drawer.logs.level[e.level]}
        </span>
      ),
    },
    { key: "source", header: p.columns.source, render: (e) => p.sources[e.source] },
    { key: "code", header: p.columns.code, render: (e) => <code className="text-[13px]">{e.code}</code> },
    { key: "message", header: p.columns.message, render: (e) => <span className="break-words">{e.message}</span> },
    {
      key: "job",
      header: p.columns.audit,
      render: (e) =>
        e.jobId ? (
          <span className="flex flex-col">
            <span>{e.targetHost || "—"}</span>
            <span className="text-[12px] text-gray-80">{e.jobId.slice(0, 8)}</span>
          </span>
        ) : (
          "—"
        ),
    },
    { key: "user", header: p.columns.user, render: (e) => e.user || "—" },
  ];

  return (
    <>
      <AdminPageHeader title={p.title} subtitle={p.subtitle} />
      <AdminTable
        title={p.tableTitle(data?.events.length ?? 0)}
        caption={p.caption}
        columns={columns}
        rows={data?.events ?? []}
        rowKey={(e) => e.id}
        status={status}
        onRetry={retry}
        emptyText={p.empty}
        minWidth={1000}
      />
    </>
  );
}
