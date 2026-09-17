"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import type { ActivityItem, ActivityKind } from "@/lib/admin/data";
import { formatDateTime, formatRelative } from "@/lib/admin/format";
import { useNow } from "@/lib/admin/useNow";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

const DOT: Record<ActivityKind, string> = {
  auditCompleted: "bg-adm-chart-completed",
  reportGenerated: "bg-adm-chart-running",
  workerStarted: "bg-adm-chart-running",
  failedJob: "bg-adm-chart-failed",
  auditFailed: "bg-adm-chart-failed",
  needsReview: "bg-adm-sev-moderate",
  userLogin: "bg-adm-chart-completed",
};

interface LiveActivityFeedProps {
  items: ActivityItem[];
  /** Whether the shell's background refresh is running; the toggle here only affects announcements + indicator. */
  paused: boolean;
  onTogglePaused: () => void;
}

export function LiveActivityFeed({ items, paused, onTogglePaused }: LiveActivityFeedProps) {
  const { t, lang } = useLanguage();
  const headingId = useId();
  const now = useNow(15_000);
  const seenIds = useRef<Set<string> | null>(null);
  const [announcement, setAnnouncement] = useState("");

  function describe(item: ActivityItem) {
    const title = `${t.admin.activity[item.kind]}${item.jobId ? ` · ${item.jobId}` : ""}`;
    const detail = t.admin.activity.detail[item.kind](item.params, item.jobId);
    return { title, detail };
  }

  // Announce only meaningful events that arrived after first render, so the
  // live region is useful rather than noisy (spec §9).
  useEffect(() => {
    if (seenIds.current === null) {
      seenIds.current = new Set(items.map((i) => i.id));
      return;
    }
    if (paused) return;
    const fresh = items.filter((i) => i.important && !seenIds.current!.has(i.id));
    items.forEach((i) => seenIds.current!.add(i.id));
    if (fresh.length > 0) {
      const { title, detail } = describe(fresh[0]);
      setAnnouncement(t.admin.overview.liveActivity.announce(`${title}. ${detail}`));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, paused]);

  return (
    <section aria-labelledby={headingId} className="rounded-2xl border border-adm-border bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id={headingId} className="text-[17px] font-semibold leading-6 text-gray-100">
            {t.admin.overview.liveActivity.title}
          </h2>
          <p className="mt-0.5 text-[13px] leading-5 text-gray-80">{t.admin.overview.liveActivity.subtitle}</p>
        </div>
        <button
          type="button"
          onClick={onTogglePaused}
          aria-pressed={paused}
          aria-label={paused ? t.admin.overview.liveActivity.resume : t.admin.overview.liveActivity.pause}
          className="inline-flex min-h-11 items-center gap-2 rounded-lg px-3 text-[13px] font-medium text-gray-80 hover:bg-gray-10"
        >
          {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
          <span aria-hidden="true" className="inline-flex items-center gap-1.5">
            <span
              className={cn(
                "inline-block h-2 w-2 rounded-full",
                paused ? "bg-gray-60" : "bg-adm-chart-completed motion-safe:animate-pulse",
              )}
            />
            {paused ? t.admin.overview.liveActivity.paused : t.admin.overview.liveActivity.autoRefresh}
          </span>
        </button>
      </div>

      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>

      <ol aria-label={t.admin.overview.liveActivity.feedLabel} className="mt-4 flex flex-col">
        {items.map((item, index) => {
          const { title, detail } = describe(item);
          return (
            <li key={item.id} className="relative flex gap-3 pb-4 last:pb-0">
              {index < items.length - 1 && (
                <span aria-hidden="true" className="absolute left-[5px] top-4 h-full w-px bg-adm-border" />
              )}
              <span aria-hidden="true" className={cn("relative mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full", DOT[item.kind])} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <p className="text-[14px] font-medium leading-5 text-gray-100">{title}</p>
                  <p className="text-[12px] leading-4 text-gray-80">
                    <time dateTime={item.at} title={formatDateTime(item.at, lang)}>
                      {now ? formatRelative(item.at, now, lang) : formatDateTime(item.at, lang)}
                    </time>
                  </p>
                </div>
                <p className="text-[13px] leading-5 text-gray-80">{detail}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
