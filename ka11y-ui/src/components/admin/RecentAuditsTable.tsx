"use client";

import { useId } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { AuditJob } from "@/lib/admin/data";
import { formatDateTime, formatNumber, formatRelative } from "@/lib/admin/format";
import { useNow } from "@/lib/admin/useNow";
import { StatusPill } from "@/components/admin/StatusPill";
import { useAdminConsole } from "@/components/admin/AdminShell";
import { useLanguage } from "@/components/dashboard/LanguageContext";

interface RecentAuditsTableProps {
  jobs: AuditJob[];
  title: string;
  subtitle?: string;
  viewAllHref?: string;
}

export function RecentAuditsTable({ jobs, title, subtitle, viewAllHref }: RecentAuditsTableProps) {
  const { t, lang } = useLanguage();
  const { openAudit } = useAdminConsole();
  const headingId = useId();
  const now = useNow(30_000);
  const columns = t.admin.overview.recentAudits.columns;

  return (
    <section aria-labelledby={headingId} className="rounded-2xl border border-adm-border bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className="flex flex-wrap items-start justify-between gap-3 p-5 pb-3">
        <div>
          <h2 id={headingId} className="text-[17px] font-semibold leading-6 text-gray-100">
            {title}
          </h2>
          {subtitle && <p className="mt-0.5 text-[13px] leading-5 text-gray-80">{subtitle}</p>}
        </div>
        {viewAllHref && (
          <Link
            href={viewAllHref}
            className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-brand-green-80 px-3 text-[14px] font-medium text-brand-green-80 hover:bg-adm-completed-bg"
          >
            {t.admin.overview.recentAudits.viewAll}
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        )}
      </div>
      {/* Scrollable region is focusable so keyboard users can reach off-screen columns. */}
      <div role="region" aria-label={t.admin.overview.recentAudits.scrollHint} tabIndex={0} className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-[14px] leading-5">
          <caption className="sr-only">{t.admin.overview.recentAudits.tableCaption}</caption>
          <thead>
            <tr className="border-y border-adm-border bg-gray-10 text-[13px] text-gray-80">
              <th scope="col" className="px-5 py-3 font-medium">{columns.targetUrl}</th>
              <th scope="col" className="px-3 py-3 text-right font-medium">{columns.pages}</th>
              <th scope="col" className="px-3 py-3 text-right font-medium">{columns.fails}</th>
              <th scope="col" className="px-3 py-3 font-medium">{columns.status}</th>
              <th scope="col" className="px-5 py-3 font-medium">{columns.created}</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className="border-b border-adm-border last:border-0">
                <th scope="row" className="max-w-[360px] px-5 py-2 font-normal">
                  <button
                    type="button"
                    onClick={() => openAudit(job)}
                    aria-label={t.admin.overview.recentAudits.openDetails(job.targetUrl)}
                    className="-mx-2 inline-flex min-h-11 items-center rounded-md px-2 text-left font-medium text-brand-green-80 underline decoration-brand-green-80/40 underline-offset-4 hover:decoration-brand-green-80"
                  >
                    <span className="break-all">{job.targetUrl}</span>
                  </button>
                </th>
                <td className="px-3 py-2 text-right tabular-nums text-gray-100">{formatNumber(job.pages, lang)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-100">{formatNumber(job.fails, lang)}</td>
                <td className="px-3 py-2">
                  <StatusPill status={job.status} />
                </td>
                <td className="px-5 py-2 text-gray-80">
                  <time dateTime={job.createdAt} title={formatDateTime(job.createdAt, lang)}>
                    {now ? formatRelative(job.createdAt, now, lang) : formatDateTime(job.createdAt, lang)}
                  </time>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
