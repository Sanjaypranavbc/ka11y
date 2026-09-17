"use client";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { AdminTable, type AdminColumn } from "@/components/admin/AdminTable";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { loadUsers } from "@/lib/admin/api";
import type { AdminAccount } from "@/lib/admin/data";
import { formatDateTime, formatNumber } from "@/lib/admin/format";
import { useAdminResource } from "@/lib/admin/useAdminResource";

export default function AdminUsersPage() {
  const { t, lang } = useLanguage();
  const p = t.admin.pages.users;
  const { data, status, retry } = useAdminResource(loadUsers);

  const columns: AdminColumn<AdminAccount>[] = [
    {
      key: "email",
      header: p.columns.email,
      render: (u) => (
        <span className="inline-flex flex-wrap items-center gap-2">
          <span className="font-medium">{u.email}</span>
          {u.isAdmin && (
            <span className="rounded-full bg-adm-completed-bg px-2 py-0.5 text-[12px] font-medium text-adm-completed">{p.adminBadge}</span>
          )}
        </span>
      ),
    },
    { key: "name", header: p.columns.name, render: (u) => u.name || "—" },
    { key: "org", header: p.columns.organization, render: (u) => u.organization || "—" },
    { key: "role", header: p.columns.role, render: (u) => u.role },
    { key: "methods", header: p.columns.methods, render: (u) => (u.signInMethods.length ? u.signInMethods.join(", ") : "—") },
    { key: "audits", header: p.columns.audits, align: "right", render: (u) => formatNumber(u.audits, lang) },
    {
      key: "lastLogin",
      header: p.columns.lastLogin,
      render: (u) => (u.lastLoginAt ? <time dateTime={u.lastLoginAt}>{formatDateTime(u.lastLoginAt, lang)}</time> : p.neverSignedIn),
    },
    { key: "created", header: p.columns.created, render: (u) => <time dateTime={u.createdAt}>{formatDateTime(u.createdAt, lang)}</time> },
  ];

  const rows = data?.users ?? [];
  const notYet = (data?.allowListed ?? []).filter((e) => !rows.some((u) => u.email.toLowerCase() === e));

  return (
    <>
      <AdminPageHeader title={p.title} subtitle={p.subtitle} />
      <AdminTable
        title={p.tableTitle(rows.length)}
        subtitle={data ? p.allowList(data.allowListed.length) : undefined}
        caption={p.caption}
        columns={columns}
        rows={rows}
        rowKey={(u) => u.id}
        status={status}
        onRetry={retry}
        emptyText={p.empty}
        minWidth={960}
      />
      {notYet.length > 0 && (
        <section className="mt-6 rounded-2xl border border-adm-border bg-white p-5">
          <h2 className="text-[15px] font-semibold leading-6 text-gray-100">{p.pendingTitle(notYet.length)}</h2>
          <p className="mt-1 text-[13px] leading-5 text-gray-80">{p.pendingBody}</p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {notYet.map((e) => (
              <li key={e} className="rounded-full bg-gray-10 px-3 py-1 text-[13px] text-gray-100">
                {e}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
