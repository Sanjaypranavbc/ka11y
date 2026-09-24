"use client";

import { useId, useRef } from "react";
import { CircleAlert, CircleCheck, CircleX, Clock, Download, ExternalLink, FileText, Play, X } from "lucide-react";
import type { AuditEvent, AuditJob, Severity } from "@/lib/admin/data";
import { SEVERITY_ORDER } from "@/lib/admin/data";
import { formatBytes, formatDateTime, formatNumber, formatTime } from "@/lib/admin/format";
import { useFocusTrap } from "@/lib/admin/useFocusTrap";
import { StatusPill } from "@/components/admin/StatusPill";
import { Tabs } from "@/components/admin/Tabs";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

const SEVERITY_DOT: Record<Severity, string> = {
  critical: "bg-adm-sev-critical",
  serious: "bg-adm-sev-serious",
  moderate: "bg-adm-sev-moderate",
  minor: "bg-adm-sev-minor",
};

const EVENT_ICON: Record<AuditEvent["code"], { Icon: typeof CircleCheck; className: string }> = {
  JOB_COMPLETED: { Icon: CircleCheck, className: "bg-adm-completed-bg text-adm-completed" },
  REPORT_GENERATED: { Icon: FileText, className: "bg-adm-running-bg text-adm-running" },
  JOB_STARTED: { Icon: Play, className: "bg-adm-running-bg text-adm-running" },
  JOB_FAILED: { Icon: CircleX, className: "bg-adm-failed-bg text-adm-failed" },
  NEEDS_REVIEW: { Icon: CircleAlert, className: "bg-adm-review-bg text-adm-review" },
};

interface AuditDetailsDrawerProps {
  job: AuditJob | null;
  onClose: () => void;
}

/**
 * Modal slide-over. Focus is trapped inside, Escape closes, focus returns to
 * the row button that opened it, and the shell marks everything else inert.
 */
export function AuditDetailsDrawer({ job, onClose }: AuditDetailsDrawerProps) {
  const { t } = useLanguage();
  const panelRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const baseId = useId();
  const open = job !== null;
  useFocusTrap(panelRef, open, { onEscape: onClose, initialFocus: headingRef });

  if (!job) return null;

  return (
    <div className="fixed inset-0 z-50">
      <div aria-hidden="true" onClick={onClose} className="absolute inset-0 bg-gray-100/40" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        tabIndex={-1}
        className="admin-drawer-enter absolute inset-y-0 right-0 flex w-full flex-col bg-white shadow-2xl sm:w-[440px] sm:border-l sm:border-adm-border"
      >
        <div className="flex items-center justify-between border-b border-adm-border px-5 py-4">
          <h2 id={`${baseId}-title`} ref={headingRef} tabIndex={-1} className="text-[20px] font-semibold leading-7 text-gray-100">
            {t.admin.drawer.title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.admin.drawer.close}
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-gray-80 hover:bg-gray-10 hover:text-gray-100"
          >
            <X size={22} aria-hidden="true" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <JobHeader job={job} />
          <Tabs
            className="mt-5"
            label={t.admin.drawer.tabsLabel}
            tabs={[
              { id: "overview", label: t.admin.drawer.tabs.overview, panel: <OverviewTab job={job} /> },
              { id: "pages", label: t.admin.drawer.tabs.pages, panel: <PagesTab job={job} /> },
              { id: "fails", label: t.admin.drawer.tabs.fails, panel: <FailsTab job={job} /> },
              { id: "reports", label: t.admin.drawer.tabs.reports, panel: <ReportsTab job={job} /> },
              { id: "logs", label: t.admin.drawer.tabs.logs, panel: <LogsTab job={job} /> },
            ]}
          />
        </div>
      </div>
    </div>
  );
}

function JobHeader({ job }: { job: AuditJob }) {
  const { t, lang } = useLanguage();
  return (
    <div className="rounded-xl border border-adm-border bg-gray-10 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="break-all text-[22px] font-semibold leading-7 text-gray-100">{job.targetHost}</h3>
        <StatusPill status={job.status} />
      </div>
      {/* Each dt/dd group sits in exactly one <div> directly under the <dl>,
          which is the only wrapper the definition-list structure allows. */}
      <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-3 text-[14px] leading-5">
        <div className="col-span-3 flex flex-wrap gap-x-3">
          <dt className="text-gray-80">{t.admin.drawer.targetUrl}</dt>
          <dd className="min-w-0">
            <a
              href={job.targetUrl}
              target="_blank"
              rel="noopener noreferrer"
              // Darker green: this link sits on the grey header, where green-80 dips under 4.5:1.
              className="inline-flex min-h-6 items-center gap-1 break-all font-medium text-brand-teal-dark underline underline-offset-4"
            >
              {job.targetUrl}
              <ExternalLink size={13} aria-hidden="true" />
              <span className="sr-only">({t.admin.drawer.opensInNewTab})</span>
            </a>
          </dd>
        </div>
        <div className="border-r border-adm-border pr-3">
          <dt className="text-gray-80">{t.admin.drawer.pages}</dt>
          <dd className="text-[20px] font-semibold leading-7 text-gray-100">{formatNumber(job.pages, lang)}</dd>
        </div>
        <div className="border-r border-adm-border pr-3">
          <dt className="text-gray-80">{t.admin.drawer.fails}</dt>
          <dd className="text-[20px] font-semibold leading-7 text-gray-100">{formatNumber(job.fails, lang)}</dd>
        </div>
        <div>
          <dt className="text-gray-80">{t.admin.drawer.depth}</dt>
          <dd className="text-[20px] font-semibold leading-7 text-gray-100">{job.depth}</dd>
        </div>
        <div className="col-span-3 sm:col-span-1">
          <dt className="inline-flex items-center gap-1.5 text-gray-80">
            <Clock size={14} aria-hidden="true" />
            {t.admin.drawer.started}
          </dt>
          <dd className="text-gray-100">
            {job.startedAt ? <time dateTime={job.startedAt}>{formatDateTime(job.startedAt, lang)}</time> : t.admin.drawer.notYet}
          </dd>
        </div>
        <div className="col-span-3 sm:col-span-2">
          <dt className="inline-flex items-center gap-1.5 text-gray-80">
            <Clock size={14} aria-hidden="true" />
            {t.admin.drawer.completed}
          </dt>
          <dd className="text-gray-100">
            {job.completedAt ? <time dateTime={job.completedAt}>{formatDateTime(job.completedAt, lang)}</time> : t.admin.drawer.notYet}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function Panel({ title, badge, children, id }: { title: string; badge?: string; children: React.ReactNode; id: string }) {
  return (
    <section aria-labelledby={id} className="rounded-xl border border-adm-border p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 id={id} className="text-[15px] font-semibold leading-5 text-gray-100">
          {title}
        </h3>
        {badge && (
          <span className="rounded-full bg-adm-completed-bg px-2.5 py-1 text-[12px] font-semibold leading-4 text-adm-completed">{badge}</span>
        )}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function OverviewTab({ job }: { job: AuditJob }) {
  const { t, lang } = useLanguage();
  const id = useId();
  return (
    <div className="flex flex-col gap-4">
      <Panel id={`${id}-summary`} title={t.admin.drawer.summary} badge={job.conformance}>
        <dl className="grid grid-cols-2 gap-3 text-[14px] leading-5">
          <div className="rounded-lg bg-gray-10 p-3">
            <dt className="text-gray-80">{t.admin.drawer.totalPages}</dt>
            <dd className="text-[20px] font-semibold leading-7 text-gray-100">{formatNumber(job.pages, lang)}</dd>
          </div>
          <div className="rounded-lg bg-gray-10 p-3">
            <dt className="text-gray-80">{t.admin.drawer.totalFails}</dt>
            <dd className="text-[20px] font-semibold leading-7 text-gray-100">{formatNumber(job.fails, lang)}</dd>
          </div>
        </dl>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <table className="w-full text-[14px] leading-5">
            <caption className="sr-only">{t.admin.drawer.severityBreakdown}</caption>
            <tbody>
              {SEVERITY_ORDER.map((sev) => (
                <tr key={sev}>
                  <th scope="row" className="py-1 text-left font-normal text-gray-100">
                    <span className="inline-flex items-center gap-2">
                      <span aria-hidden="true" className={cn("inline-block h-2.5 w-2.5 rounded-full", SEVERITY_DOT[sev])} />
                      {t.admin.severity[sev]}
                    </span>
                  </th>
                  <td className="py-1 text-right font-medium tabular-nums text-gray-100">{formatNumber(job.severity[sev], lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="flex flex-col gap-2 text-[14px] leading-5 sm:border-l sm:border-adm-border sm:pl-3">
            <div className="flex items-center justify-between gap-2">
              <dt className="inline-flex items-center gap-2 text-gray-100">
                <CircleCheck size={16} aria-hidden="true" className="text-adm-completed" />
                {t.admin.drawer.passed}
              </dt>
              <dd className="font-medium tabular-nums text-gray-100">{formatNumber(job.passed, lang)}</dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="inline-flex items-center gap-2 text-gray-100">
                <CircleAlert size={16} aria-hidden="true" className="text-adm-review" />
                {t.admin.drawer.needsReview}
              </dt>
              <dd className="font-medium tabular-nums text-gray-100">{formatNumber(job.needsReview, lang)}</dd>
            </div>
          </dl>
        </div>
      </Panel>

      <Panel id={`${id}-job`} title={t.admin.drawer.jobInfo}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[14px] leading-5">
          <dt className="text-gray-80">{t.admin.drawer.user}</dt>
          <dd className="break-all text-gray-100">{job.user}</dd>
          <dt className="text-gray-80">{t.admin.drawer.organization}</dt>
          <dd className="text-gray-100">{job.organization}</dd>
          <dt className="text-gray-80">{t.admin.drawer.crawlDepth}</dt>
          <dd className="text-gray-100">{job.depth}</dd>
          <dt className="text-gray-80">{t.admin.drawer.status}</dt>
          <dd>
            <StatusPill status={job.status} />
          </dd>
        </dl>
      </Panel>

      <Panel id={`${id}-actions`} title={t.admin.drawer.actions}>
        <div className="flex flex-col gap-2">
          <a
            href={job.reportHref}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-brand-green-80 px-4 text-[14px] font-medium text-brand-green-80 hover:bg-adm-completed-bg"
          >
            <FileText size={16} aria-hidden="true" />
            {t.admin.drawer.viewReport}
          </a>
          <a
            href={job.csvHref}
            download
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-brand-green-80 px-4 text-[14px] font-medium text-brand-green-80 hover:bg-adm-completed-bg"
          >
            <Download size={16} aria-hidden="true" />
            {t.admin.drawer.downloadCsv}
          </a>
          <a
            href={job.s3Href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-brand-green-80 px-4 text-[14px] font-medium text-white hover:bg-brand-teal-dark"
          >
            <ExternalLink size={16} aria-hidden="true" />
            {t.admin.drawer.viewInS3}
            <span className="sr-only">({t.admin.drawer.opensInNewTab})</span>
          </a>
        </div>
      </Panel>

      <Panel id={`${id}-events`} title={t.admin.drawer.recentEvents}>
        <ol className="flex flex-col divide-y divide-adm-border">
          {job.events.map((event) => {
            const { Icon, className } = EVENT_ICON[event.code];
            return (
              <li key={`${event.code}-${event.at}`} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                <span aria-hidden="true" className={cn("inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full", className)}>
                  <Icon size={14} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="text-[13px] font-semibold uppercase leading-5 tracking-wide text-gray-100">
                      <span aria-hidden="true">{event.code}</span>
                      <span className="sr-only">{t.admin.drawer.eventCodes[event.code]}</span>
                    </p>
                    <time dateTime={event.at} className="text-[12px] leading-4 text-gray-80">
                      {formatTime(event.at, lang)}
                    </time>
                  </div>
                  <p className="text-[13px] leading-5 text-gray-80">{event.message}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </Panel>
    </div>
  );
}

function PagesTab({ job }: { job: AuditJob }) {
  const { t, lang } = useLanguage();
  const c = t.admin.drawer.pagesTable;
  if (job.pageList.length === 0) return <p className="text-[14px] leading-5 text-gray-80">{c.empty}</p>;
  return (
    <table className="w-full text-[14px] leading-5">
      <caption className="sr-only">{c.caption(job.targetUrl)}</caption>
      <thead>
        <tr className="border-b border-adm-border text-left text-[13px] text-gray-80">
          <th scope="col" className="py-2 pr-2 font-medium">{c.url}</th>
          <th scope="col" className="py-2 pr-2 text-right font-medium">{c.fails}</th>
          <th scope="col" className="py-2 font-medium">{c.status}</th>
        </tr>
      </thead>
      <tbody>
        {job.pageList.map((page) => (
          <tr key={page.url} className="border-b border-adm-border last:border-0">
            <td className="break-all py-2 pr-2 text-gray-100">{page.url}</td>
            <td className="py-2 pr-2 text-right tabular-nums text-gray-100">{formatNumber(page.fails, lang)}</td>
            <td className="py-2">
              <StatusPill status={page.status} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FailsTab({ job }: { job: AuditJob }) {
  const { t, lang } = useLanguage();
  const c = t.admin.drawer.failsTable;
  if (job.failList.length === 0) return <p className="text-[14px] leading-5 text-gray-80">{c.empty}</p>;
  return (
    <table className="w-full text-[14px] leading-5">
      <caption className="sr-only">{c.caption(job.targetUrl)}</caption>
      <thead>
        <tr className="border-b border-adm-border text-left text-[13px] text-gray-80">
          <th scope="col" className="py-2 pr-2 font-medium">{c.criterion}</th>
          <th scope="col" className="py-2 pr-2 font-medium">{c.title}</th>
          <th scope="col" className="py-2 pr-2 font-medium">{c.severity}</th>
          <th scope="col" className="py-2 text-right font-medium">{c.occurrences}</th>
        </tr>
      </thead>
      <tbody>
        {job.failList.map((fail) => (
          <tr key={fail.id} className="border-b border-adm-border last:border-0 align-top">
            <td className="py-2 pr-2 tabular-nums text-gray-100">{fail.criterion}</td>
            <td className="py-2 pr-2 text-gray-100">{fail.title}</td>
            <td className="py-2 pr-2 text-gray-100">
              <span className="inline-flex items-center gap-2 whitespace-nowrap">
                <span aria-hidden="true" className={cn("inline-block h-2.5 w-2.5 rounded-full", SEVERITY_DOT[fail.severity])} />
                {t.admin.severity[fail.severity]}
              </span>
            </td>
            <td className="py-2 text-right tabular-nums text-gray-100">{formatNumber(fail.occurrences, lang)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ReportsTab({ job }: { job: AuditJob }) {
  const { t, lang } = useLanguage();
  const c = t.admin.drawer.reportsList;
  if (job.reports.length === 0) return <p className="text-[14px] leading-5 text-gray-80">{c.empty}</p>;
  return (
    <ul className="flex flex-col gap-2">
      {job.reports.map((report) => (
        <li key={report.id} className="flex items-center justify-between gap-3 rounded-lg border border-adm-border p-3">
          <div className="min-w-0 text-[14px] leading-5">
            <p className="font-medium text-gray-100">{report.label}</p>
            <p className="text-[13px] text-gray-80">
              <span className="sr-only">{c.size}: </span>
              {formatBytes(report.sizeBytes, lang)}
              {" · "}
              <span className="sr-only">{c.generated}: </span>
              <time dateTime={report.createdAt}>{formatDateTime(report.createdAt, lang)}</time>
            </p>
          </div>
          <a
            href={report.href}
            download
            aria-label={c.download(report.label)}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-brand-green-80 text-brand-green-80 hover:bg-adm-completed-bg"
          >
            <Download size={18} aria-hidden="true" />
          </a>
        </li>
      ))}
    </ul>
  );
}

function LogsTab({ job }: { job: AuditJob }) {
  const { t, lang } = useLanguage();
  const c = t.admin.drawer.logs;
  if (job.logs.length === 0) return <p className="text-[14px] leading-5 text-gray-80">{c.empty}</p>;
  const LEVEL: Record<"info" | "warn" | "error", string> = {
    info: "text-gray-80",
    warn: "text-adm-review",
    error: "text-adm-failed",
  };
  return (
    <ol aria-label={c.heading} className="flex flex-col gap-2 rounded-lg bg-gray-10 p-3 font-mono text-[13px] leading-5">
      {job.logs.map((line) => (
        <li key={`${line.at}-${line.message}`} className="grid grid-cols-[auto_auto_1fr] gap-x-3">
          <time dateTime={line.at} className="text-gray-80">
            {formatTime(line.at, lang)}
          </time>
          <span className={cn("font-semibold uppercase", LEVEL[line.level])}>
            <span aria-hidden="true">{line.level}</span>
            <span className="sr-only">{c.level[line.level]}</span>
          </span>
          <span className="break-words text-gray-100">{line.message}</span>
        </li>
      ))}
    </ol>
  );
}
