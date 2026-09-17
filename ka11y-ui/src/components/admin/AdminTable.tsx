"use client";

import { useId, type ReactNode } from "react";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import type { ResourceState } from "@/lib/admin/useAdminResource";

export interface AdminColumn<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  /** Cell renderer; the first column is the row header. */
  render: (row: T) => ReactNode;
}

interface AdminTableProps<T> {
  title: string;
  subtitle?: string;
  caption: string;
  columns: AdminColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  status: ResourceState;
  onRetry?: () => void;
  emptyText: string;
  actions?: ReactNode;
  minWidth?: number;
}

/**
 * Accessible data table used by the admin list pages: a real <table> with a
 * caption and row headers, a focusable scroll region for narrow viewports,
 * and a polite status line for loading/error/empty (WCAG 1.3.1, 4.1.3).
 */
export function AdminTable<T>({
  title,
  subtitle,
  caption,
  columns,
  rows,
  rowKey,
  status,
  onRetry,
  emptyText,
  actions,
  minWidth = 720,
}: AdminTableProps<T>) {
  const { t } = useLanguage();
  const headingId = useId();
  const common = t.admin.pages.common;

  return (
    <section aria-labelledby={headingId} className="rounded-2xl border border-adm-border bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className="flex flex-wrap items-start justify-between gap-3 p-5 pb-3">
        <div>
          <h2 id={headingId} className="text-[17px] font-semibold leading-6 text-gray-100">
            {title}
          </h2>
          {subtitle && <p className="mt-0.5 text-[13px] leading-5 text-gray-80">{subtitle}</p>}
        </div>
        {actions}
      </div>

      <div role="status" aria-live="polite" className={status === "ready" ? "sr-only" : "px-5 pb-4 text-[14px] leading-5 text-gray-80"}>
        {status === "loading" && common.loading}
        {status === "error" && (
          <>
            {common.loadError}{" "}
            {onRetry && (
              <button type="button" onClick={onRetry} className="min-h-11 rounded-md px-2 font-medium text-brand-green-80 underline underline-offset-4">
                {common.retry}
              </button>
            )}
          </>
        )}
      </div>

      {status !== "error" && (
        <div role="region" aria-label={common.scrollHint} tabIndex={0} className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-[14px] leading-5" style={{ minWidth }}>
            <caption className="sr-only">{caption}</caption>
            <thead>
              <tr className="border-y border-adm-border bg-gray-10 text-[13px] text-gray-80">
                {columns.map((c, i) => (
                  <th
                    key={c.key}
                    scope="col"
                    className={`py-3 font-medium ${i === 0 ? "px-5" : i === columns.length - 1 ? "px-5" : "px-3"} ${c.align === "right" ? "text-right" : ""}`}
                  >
                    {c.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && status === "ready" && (
                <tr>
                  <td colSpan={columns.length} className="px-5 py-8 text-center text-gray-80">
                    {emptyText}
                  </td>
                </tr>
              )}
              {rows.map((row) => (
                <tr key={rowKey(row)} className="border-b border-adm-border last:border-0">
                  {columns.map((c, i) =>
                    i === 0 ? (
                      <th key={c.key} scope="row" className="px-5 py-2.5 font-normal text-gray-100">
                        {c.render(row)}
                      </th>
                    ) : (
                      <td
                        key={c.key}
                        className={`py-2.5 text-gray-100 ${i === columns.length - 1 ? "px-5" : "px-3"} ${c.align === "right" ? "text-right tabular-nums" : ""}`}
                      >
                        {c.render(row)}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
