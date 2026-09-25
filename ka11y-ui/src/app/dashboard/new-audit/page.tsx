"use client";

import { Suspense, useState, useEffect, useMemo, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, ChevronRight, ExternalLink } from "lucide-react";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { DownloadReportMenu } from "@/components/dashboard/DownloadActions";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { useRunningAudit } from "@/components/dashboard/RunningAuditContext";
import { computeRealProgress, isActive } from "@/lib/runningAudit";
import type { Translations } from "@/lib/i18n/translations";
import { cn } from "@/lib/utils";
import { redirectToLogin } from "@/lib/auth";

type WcagLevel = "A" | "AA" | "AAA";
function buildScanSteps(t: Translations) {
  return [
    { id: "axe-header",      type: "header" as const, label: t.newAudit.steps.axeHeader },
    { id: "img-alt",         type: "step"   as const, label: t.newAudit.steps.imgAlt,         findings: 17 },
    { id: "unified",         type: "step"   as const, label: t.newAudit.steps.unified,        findings: 92 },
    { id: "form-fields",     type: "step"   as const, label: t.newAudit.steps.formFields,     findings: 12 },
    { id: "moving",          type: "step"   as const, label: t.newAudit.steps.moving,         findings:  0 },
    { id: "text-spacing",    type: "step"   as const, label: t.newAudit.steps.textSpacing,    findings: 18 },
    { id: "rendered-header", type: "header" as const, label: t.newAudit.steps.renderedHeader },
    { id: "media",           type: "step"   as const, label: t.newAudit.steps.media,          findings:  2 },
    { id: "sensory",         type: "step"   as const, label: t.newAudit.steps.sensory,        findings:  1 },
    { id: "consistent-nav",  type: "step"   as const, label: t.newAudit.steps.consistentNav,  findings:  0 },
    { id: "consistent-id",   type: "step"   as const, label: t.newAudit.steps.consistentId,   findings:  3 },
    { id: "unusual",         type: "step"   as const, label: t.newAudit.steps.unusual,        findings:  4 },
    { id: "section",         type: "step"   as const, label: t.newAudit.steps.section,        findings:  2 },
  ];
}

function DoneIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="#00AC8F" />
      <path d="M8 12l3 3 5-5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RingIcon({ spin }: { spin: boolean }) {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={spin ? "animate-spin" : undefined}
    >
      <circle cx="12" cy="12" r="9" stroke="#D7D7CF" strokeWidth="1.5" />
      {spin && (
        <path
          d="M12 3a9 9 0 0 1 9 9"
          stroke="#9F9F9F"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}

function NewAuditPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t, lang } = useLanguage();
  const { running, start, cancel, dismiss } = useRunningAudit();
  const SCAN_STEPS = useMemo(() => buildScanSteps(t), [t]);
  const ACTUAL_STEPS = useMemo(() => SCAN_STEPS.filter((s) => s.type === "step"), [SCAN_STEPS]);
  const [url, setUrl] = useState("");
  const [depth, setDepth] = useState(0);
  const [showCrawlTooltip, setShowCrawlTooltip] = useState(false);
  const [wcagLevel, setWcagLevel] = useState<WcagLevel>("AA");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Arrived here because another screen is locked (AuditLockGuard).
  const lockedNotice = searchParams.get("locked") === "1";

  const totalSteps = ACTUAL_STEPS.length;
  // The run itself lives in RunningAuditContext (root layout): it keeps
  // polling while the user is elsewhere and is restored from localStorage
  // after a refresh, so this page only renders whatever state it is in.
  const scanning = running !== null && isActive(running.status);
  const completed = running?.status === "completed";
  const progress = running ? computeRealProgress(running.stages, running.status) : 0;

  // Cosmetic step animation only — advances the visible step list while the
  // real audit runs. Derived from elapsed time (not a counter) so it resumes
  // at the right step when the page is remounted mid-run. Capped one step
  // short of totalSteps; only a real "completed" shows every step done.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!scanning) return;
    const timer = setInterval(() => setNow(Date.now()), 1200);
    return () => clearInterval(timer);
  }, [scanning]);
  const completedCount = completed
    ? totalSteps
    : running
      ? Math.min(totalSteps - 1, Math.floor((now - running.startedAt) / 1200))
      : 0;
  const isDone = completedCount >= totalSteps;

  // A run that finished while this page was mounted lands on the dashboard
  // after a brief pause (the result is already in AuditDataContext). A run
  // found already finished on arrival shows the "Audit complete" screen
  // with a button instead, so the outcome is visible.
  const wasScanning = useRef(false);
  const confirmed = running?.confirmed ?? false;
  useEffect(() => {
    // Only a confirmed in-progress poll counts, not the placeholder rebuilt
    // from localStorage: a run that finished while this tab was closed must
    // show "Audit complete" rather than bounce to the dashboard.
    if (scanning && confirmed) wasScanning.current = true;
    if (completed && wasScanning.current) {
      const timer = setTimeout(() => {
        dismiss();
        router.push("/dashboard");
      }, 600);
      return () => clearTimeout(timer);
    }
  }, [scanning, confirmed, completed, dismiss, router]);

  // Failed / cancelled / unknown: the reason shows on the form (derived, not
  // stored) until the next run replaces it.
  const outcomeError =
    running?.status === "failed"
      ? (running.error ?? t.newAudit.errorGeneric)
      : running?.status === "cancelled"
        ? t.newAudit.cancelledMessage
        : running?.status === "unknown"
          ? running.error === "still_running"
            ? t.newAudit.errorStillRunning
            : running.error === "unreachable"
              ? t.newAudit.errorUnreachable
              : t.newAudit.unknownMessage
          : null;
  const shownError = error ?? outcomeError;

  async function handleCancel() {
    setCancelling(true);
    const ok = await cancel();
    setCancelling(false);
    if (!ok) setError(t.newAudit.cancelFailed);
  }

  async function handleRun() {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      setError(t.newAudit.errorEmptyUrl);
      return;
    }

    // A multi-page crawl runs longer than the browser will wait, so its result
    // is delivered by email — without an address there is no way to hand it back.
    const trimmedEmail = email.trim();
    if (depth > 0 && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(trimmedEmail)) {
      setError(t.newAudit.errorEmailRequired);
      return;
    }

    setError(null);
    setSubmitting(true);

    try {
      const res = await fetch("/api/wcag-audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: trimmedUrl,
          maxDepth: depth,
          wcagLevel,
          email: trimmedEmail || undefined,
          // The backend renders every reason/criterion string server-side and
          // defaults to detecting the *audited page's* language. Without this
          // the dashboard chrome follows the toggle while the findings come
          // back in the site's language — JA selected, English site, English
          // reasons. The toggle is the user's choice, so it wins.
          lang,
        }),
      });
      const data = await res.json().catch(() => null);

      if (res.status === 401) {
        // Session gone (expired server-side or cookie cleared): back to login.
        await redirectToLogin();
        return;
      }

      if (!res.ok || !data?.jobId) {
        setError(data?.error ?? t.newAudit.errorGeneric);
        setSubmitting(false);
        return;
      }

      // Hand the job to the shared run loop; deep crawls are tracked the
      // same way (the report is additionally emailed when they finish).
      start({ jobId: data.jobId, url: trimmedUrl, depth, email: trimmedEmail, startedAt: Date.now() });
      setSubmitting(false);
    } catch {
      setError(t.newAudit.errorUnreachable);
      setSubmitting(false);
    }
  }


  /* ─── Completed screen (run finished while the user was elsewhere) ─── */
  if (completed && running) {
    return (
      <>
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-gray-10 px-4 py-4 sm:h-20 sm:px-8 sm:py-0 lg:px-16">
          <div className="flex flex-wrap items-center gap-2 sm:gap-4">
            <span className="text-[24px] font-medium leading-tight text-brand-teal sm:text-[32px] sm:leading-[42px]">A11Y</span>
          </div>
          <LanguageToggle />
        </header>

        <main className="flex flex-1 items-center justify-center px-4 py-6 sm:px-8 lg:px-16">
          <div className="flex w-full max-w-[560px] flex-col items-center gap-4 rounded-[16px] bg-gray-10 px-6 py-10 text-center sm:px-10">
            <CheckCircle2 size={48} className="text-brand-teal-dark" aria-hidden="true" />
            <h2 className="text-[20px] font-medium leading-7 text-gray-100 sm:text-[24px]">
              {t.newAudit.completedTitle}
            </h2>
            <p className="text-[14px] leading-6 text-gray-80 sm:text-[16px]">
              {t.newAudit.completedMessage(running.url)}
            </p>
            <button
              type="button"
              onClick={() => {
                dismiss();
                router.push("/dashboard");
              }}
              className="mt-2 h-12 rounded-[8px] bg-brand-teal-dark px-6 text-[16px] leading-6 text-white"
            >
              {t.newAudit.viewResults}
            </button>
          </div>
        </main>
      </>
    );
  }

  /* ─── Scanning screen ─── */
  if (scanning && running) {
    let actualIdx = 0;

    return (
      <>
        {/* Header — shows target URL while scanning */}
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-gray-10 px-4 py-4 sm:h-20 sm:px-8 sm:py-0 lg:px-16">
          <div className="flex flex-wrap items-center gap-2 sm:gap-4">
            <span className="text-[24px] font-medium leading-tight text-brand-teal sm:text-[32px] sm:leading-[42px]">A11Y</span>
            <div className="flex items-center gap-1.5 text-[14px] leading-6 sm:text-[16px]">
              <span className="text-brand-green-80">Target :</span>
              <span className="hidden text-[#65605A] sm:inline">{running.url || url || "https://samplesite.com/"}</span>
              <ExternalLink size={14} className="shrink-0 text-brand-green-80" />
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-6">
            <LanguageToggle />
            <DownloadReportMenu />
          </div>
        </header>

        <main className="flex flex-1 px-4 py-6 sm:px-8 sm:py-8 lg:px-16 lg:py-10">
          <div className="w-full rounded-[16px] bg-gray-10 px-4 py-6 flex flex-col gap-6 sm:px-10 sm:py-10">

            {(lockedNotice || running.depth > 0 || error) && (
              <div className="flex flex-col gap-2">
                {lockedNotice && (
                  <p role="status" className="rounded-[8px] border border-brand-green-80 bg-white px-4 py-3 text-[14px] leading-6 text-gray-100">
                    {t.newAudit.lockedNotice}
                  </p>
                )}
                {running.depth > 0 && running.email && (
                  <p className="text-[14px] leading-6 text-gray-80">{t.newAudit.deepCrawlNote(running.email)}</p>
                )}
                {error && (
                  <p role="alert" className="text-[14px] leading-6 text-red-600">{error}</p>
                )}
              </div>
            )}

            {/* Progress bar */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-[14px] leading-6 text-gray-100 sm:text-[16px]">
                <span>{t.newAudit.auditProgress}</span>
                <span>{progress}%</span>
              </div>
              <div className="relative h-2 w-full overflow-hidden rounded-full bg-gray-40">
                <div
                  className="absolute left-0 top-0 h-full rounded-full bg-brand-teal-dark transition-all duration-700 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {/* Steps */}
            <div className="flex flex-col gap-4">
              {SCAN_STEPS.map((step) => {
                if (step.type === "header") {
                  return (
                    <div key={step.id} className="flex items-center gap-2">
                      <RingIcon spin={!isDone} />
                      <span className="text-[13px] leading-6 text-gray-100 sm:text-[16px]">{step.label}</span>
                    </div>
                  );
                }

                const myIdx = actualIdx++;
                const status =
                  myIdx < completedCount ? "done" :
                  myIdx === completedCount ? "active" :
                  "pending";

                return (
                  <div key={step.id} className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      {status === "done" ? <DoneIcon /> : <RingIcon spin={status === "active"} />}
                      <span className="text-[13px] leading-6 text-gray-100 sm:text-[16px]">{step.label}</span>
                    </div>
                    {status === "done" && (
                      <span className="shrink-0 text-[13px] leading-6 text-gray-100 sm:text-[16px]">
                        {t.newAudit.findingsCount(step.findings)}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Never a dead end: the audit can be cancelled from here. */}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleCancel}
                disabled={cancelling}
                className="h-11 rounded-[8px] border border-brand-green-80 px-5 text-[14px] font-medium text-brand-green-80 hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {cancelling ? t.newAudit.cancelling : t.newAudit.cancel}
              </button>
            </div>

          </div>
        </main>
      </>
    );
  }

  /* ─── Form screen ─── */
  return (
    <>
      {/* Top header */}
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-gray-10 px-4 py-4 sm:h-20 sm:px-8 sm:py-0 lg:px-16">
        <span className="text-[24px] font-medium leading-tight text-brand-teal sm:text-[32px] sm:leading-[42px]">A11Y</span>
        <div className="flex items-center gap-2 sm:gap-6">
          <LanguageToggle />
          <DownloadReportMenu />
        </div>
      </header>

      <main className="flex flex-1 justify-center px-4 py-6 sm:px-8 sm:py-8 lg:px-16 lg:py-10">
        <div className="w-full max-w-[759px]">

          {/* Page heading */}
          <div className="border-b border-gray-40 pb-4">
            <h1 className="text-[24px] font-medium leading-[32px] text-gray-100">{t.newAudit.heading}</h1>
            <p className="mt-2 text-[18px] leading-[26px] text-gray-80">
              {t.newAudit.subheading}
            </p>
          </div>

          {/* Form card */}
          <div className="mt-8 flex flex-col gap-6 rounded-[16px] bg-gray-10 px-4 py-6 sm:px-8 sm:py-8 lg:px-16 lg:py-10">

            {/* Target URL */}
            <div className="flex flex-col gap-2">
              <label htmlFor="target-url" className="text-[16px] leading-6 text-gray-100">
                {t.newAudit.targetUrlLabel}
              </label>
              <input
                id="target-url"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder={t.newAudit.targetUrlPlaceholder}
                className="h-12 w-full rounded-[8px] border border-gray-60 bg-white px-4 text-[16px] leading-6 text-gray-100 placeholder:text-gray-60 focus:border-brand-teal focus:outline-none"
              />
            </div>

            {/* Crawl Depth + WCAG Level */}
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6">

              {/* Crawl Depth */}
              <div className="relative flex flex-1 flex-col gap-2">
                <div className="flex items-center gap-1.5">
                  <label htmlFor="max-depth" className="text-[16px] leading-6 text-gray-100">
                    {t.newAudit.maxDepthLabel}
                  </label>
                  <button
                    type="button"
                    onClick={() => setShowCrawlTooltip((prev) => !prev)}
                    onMouseEnter={() => setShowCrawlTooltip(true)}
                    onMouseLeave={() => setShowCrawlTooltip(false)}
                    aria-label="Crawl depth information"
                    className="inline-flex items-center justify-center text-brand-teal transition-transform hover:scale-105 focus:outline-none"
                  >
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="10" r="8.5" stroke="#00AC8F" strokeWidth="1.8" fill="white" />
                      <path d="M10 5.8V11.2M10 13.8V14.2" stroke="#00AC8F" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  </button>
                </div>

                {/* Helper Tooltip Popover */}
                {showCrawlTooltip && (
                  <div
                    className="absolute left-0 top-9 z-50 w-[300px] sm:w-[350px] rounded-[12px] border border-gray-200 bg-white p-4 sm:p-5 shadow-xl transition-all"
                    onMouseEnter={() => setShowCrawlTooltip(true)}
                    onMouseLeave={() => setShowCrawlTooltip(false)}
                  >
                    {t.newAudit.crawlDepthLevels.map((lvl, idx) => (
                      <div key={idx} className={cn(idx > 0 && "mt-4 border-t border-gray-100 pt-4")}>
                        <h4 className="text-[14px] font-bold text-gray-900">{lvl.label}</h4>
                        {lvl.bullets ? (
                          <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[13px] leading-relaxed text-gray-600">
                            {lvl.bullets.map((line) => (
                              <li key={line}>{line}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-1.5 text-[13px] leading-relaxed text-gray-600">{lvl.body}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex h-12 items-center justify-between rounded-[8px] border border-gray-40 bg-white px-4">
                  <span className="text-[16px] leading-6 text-gray-100">{depth}</span>
                  <div className="flex flex-col gap-1">
                    <button
                      type="button"
                      onClick={() => setDepth((d) => d + 1)}
                      aria-label={t.newAudit.increaseDepth}
                      className="flex h-4 w-4 items-center justify-center text-gray-60 hover:text-gray-100"
                    >
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path d="M4 10L8 6L12 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </button>
                    <button
                      type="button"
                      onClick={() => setDepth((d) => Math.max(0, d - 1))}
                      aria-label={t.newAudit.decreaseDepth}
                      className="flex h-4 w-4 items-center justify-center text-gray-60 hover:text-gray-100"
                    >
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path d="M4 6L8 10L12 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </button>
                  </div>
                </div>
              </div>

              {/* WCAG Level */}
              <div className="flex flex-1 flex-col gap-2">
                <span className="text-[16px] leading-6 text-gray-100">{t.newAudit.wcagLevelLabel}</span>
                <div className="flex items-center gap-2" role="radiogroup" aria-label={t.newAudit.wcagLevelLabel}>
                  {(["A", "AA", "AAA"] as WcagLevel[]).map((level) => (
                    <button
                      key={level}
                      type="button"
                      role="radio"
                      aria-checked={wcagLevel === level}
                      onClick={() => setWcagLevel(level)}
                      className={cn(
                        "h-12 flex-1 rounded-[8px] border text-[16px] leading-6 transition-colors",
                        wcagLevel === level
                          ? "border-brand-teal bg-brand-green-20 text-brand-teal-dark"
                          : "border-transparent bg-white text-gray-80 hover:border-gray-40",
                      )}
                    >
                      {level}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Notification email */}
            <div className="flex flex-col gap-2">
              <label htmlFor="notify-email" className="text-[16px] leading-6 text-gray-100">
                {t.newAudit.notificationEmailLabel}
              </label>
              <input
                id="notify-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t.newAudit.notificationEmailPlaceholder}
                className="h-12 w-full rounded-[8px] border border-gray-40 bg-white px-4 text-[16px] leading-6 text-gray-100 placeholder:text-gray-60 focus:border-brand-teal focus:outline-none"
              />
            </div>

            {/* Submit */}
            {shownError && (
              <p role="alert" className="text-[14px] leading-6 text-red-600">
                {shownError}
              </p>
            )}
            <button
              type="button"
              onClick={handleRun}
              disabled={submitting}
              className="flex w-full items-center justify-center gap-2 rounded-[16px] bg-brand-green-80 px-6 py-4 text-[16px] font-medium leading-6 text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <ChevronRight size={18} className="stroke-[2.5]" aria-hidden="true" />
              {submitting ? t.newAudit.submitting : t.newAudit.submit}
            </button>
          </div>

        </div>
      </main>
    </>
  );
}

export default function NewAuditPageWithParams() {
  return (
    <Suspense fallback={null}>
      <NewAuditPage />
    </Suspense>
  );
}
