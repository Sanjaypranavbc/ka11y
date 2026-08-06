"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowUp, ExternalLink } from "lucide-react";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { DownloadCsvButton } from "@/components/dashboard/DownloadActions";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import type { Translations } from "@/lib/i18n/translations";
import type { WcagAuditResponse } from "@/lib/wcagAudit";
import { cn } from "@/lib/utils";

type WcagLevel = "A" | "AA" | "AAA";
type ScanPhase = "form" | "scanning";

interface JobStage {
  name: string;
  status: string;
  findings_count?: number;
}

// Mirrors ka11y-python/ka11y/api/v1/combined/constants.py STAGE_WEIGHTS —
// the only two stages the backend actually tracks lifecycle for.
const STAGE_WEIGHTS: Record<string, number> = { image_audit: 62, media_audit: 38 };
const STAGE_WEIGHT_TOTAL = Object.values(STAGE_WEIGHTS).reduce((a, b) => a + b, 0);

// Real progress from the backend's own stage lifecycle (poll response),
// not a local timer. A stage only counts once the API reports it
// completed/errored; the final jump to 100 is gated on job status
// "completed" so post-stage report building/merging isn't shown as done
// early.
function computeRealProgress(stages: JobStage[], jobStatus: string | null): number {
  if (jobStatus === "completed") return 100;
  const done = stages.reduce((sum, s) => {
    if (s.status === "completed" || s.status === "error") {
      return sum + (STAGE_WEIGHTS[s.name] ?? 0);
    }
    return sum;
  }, 0);
  return Math.min(95, Math.round((done / STAGE_WEIGHT_TOTAL) * 100));
}

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

export default function NewAuditPage() {
  const router = useRouter();
  const { setAuditData } = useAuditData();
  const { t } = useLanguage();
  const SCAN_STEPS = useMemo(() => buildScanSteps(t), [t]);
  const ACTUAL_STEPS = useMemo(() => SCAN_STEPS.filter((s) => s.type === "step"), [SCAN_STEPS]);
  const [url, setUrl] = useState("");
  const [depth, setDepth] = useState(2);
  const [wcagLevel, setWcagLevel] = useState<WcagLevel>("AA");
  const [email, setEmail] = useState("");
  const [phase, setPhase] = useState<ScanPhase>("form");
  const [completedCount, setCompletedCount] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<WcagAuditResponse | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStages, setJobStages] = useState<JobStage[]>([]);
  const [jobStatus, setJobStatus] = useState<string | null>(null);

  const totalSteps = ACTUAL_STEPS.length;
  const isDone = completedCount >= totalSteps;
  // The percentage shown is driven entirely by the real backend stage data
  // polled below — it is not a function of the cosmetic step animation.
  const progress = computeRealProgress(jobStages, jobStatus);

  // Cosmetic step animation only — advances the visible step list while the
  // real audit runs in the background. Capped one step short of totalSteps
  // so it can never reach 100% on its own; only the real poll result
  // (data.status === "completed") is allowed to call setCompletedCount(totalSteps).
  useEffect(() => {
    if (phase !== "scanning" || isDone) return;
    if (completedCount >= totalSteps - 1) return;
    const timer = setTimeout(() => setCompletedCount((c) => c + 1), 1200);
    return () => clearTimeout(timer);
  }, [phase, completedCount, isDone, totalSteps]);

  async function handleRun() {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      setError(t.newAudit.errorEmptyUrl);
      return;
    }

    setError(null);
    setSubmitting(true);
    setCompletedCount(0);
    setScanResult(null);
    setJobId(null);
    setJobStages([]);
    setJobStatus(null);
    setPhase("scanning");

    try {
      const res = await fetch("/api/wcag-audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmedUrl, depth, wcagLevel }),
      });
      const data = await res.json().catch(() => null);

      if (!res.ok || !data?.jobId) {
        setPhase("form");
        setError(data?.error ?? t.newAudit.errorGeneric);
        setSubmitting(false);
        return;
      }

      setJobId(data.jobId);
    } catch {
      setPhase("form");
      setError(t.newAudit.errorUnreachable);
      setSubmitting(false);
    }
  }

  // Polls the job status from the browser in short-lived requests instead of
  // holding one connection open for the whole audit — a reverse proxy in
  // front of the app (Apache/nginx/ALB) will kill a single long-lived
  // request well before a real audit (routinely 100s+) finishes.
  useEffect(() => {
    if (phase !== "scanning" || !jobId || scanResult) return;

    let cancelled = false;
    const startTime = Date.now();
    const TIMEOUT_MS = 300000;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const res = await fetch(`/api/wcag-audit/${jobId}`);
        const data = await res.json().catch(() => null);
        if (cancelled) return;

        if (!res.ok) {
          setPhase("form");
          setError(data?.error ?? t.newAudit.errorGeneric);
          setSubmitting(false);
          return;
        }

        // Real stage lifecycle from the backend — drives the progress bar
        // (see computeRealProgress) independently of the cosmetic step list.
        setJobStages((data.stages as JobStage[]) ?? []);
        setJobStatus(data.status ?? null);

        if (data.status === "completed") {
          setScanResult(data.result as WcagAuditResponse);
          setAuditData(data.result as WcagAuditResponse);
          setCompletedCount(totalSteps);
          setSubmitting(false);
          // Brief pause so the user sees every step marked done before the
          // redirect, then land on the dashboard with the real result already
          // in AuditDataContext (no modal — straight to the real data).
          setTimeout(() => router.push("/dashboard"), 600);
          return;
        }

        if (data.status === "failed" || data.status === "cancelled") {
          setPhase("form");
          setError(data.error ?? t.newAudit.errorGeneric);
          setSubmitting(false);
          return;
        }

        if (Date.now() - startTime > TIMEOUT_MS) {
          setPhase("form");
          setError(t.newAudit.errorGeneric);
          setSubmitting(false);
          return;
        }

        timer = setTimeout(poll, 3000);
      } catch {
        if (!cancelled) {
          setPhase("form");
          setError(t.newAudit.errorUnreachable);
          setSubmitting(false);
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [phase, jobId, scanResult, totalSteps, t, setAuditData, router]);

  /* ─── Scanning screen ─── */
  if (phase === "scanning") {
    let actualIdx = 0;

    return (
      <>
        {/* Header — shows target URL while scanning */}
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-gray-10 px-4 py-4 sm:h-20 sm:px-8 sm:py-0 lg:px-16">
          <div className="flex flex-wrap items-center gap-2 sm:gap-4">
            <span className="text-[24px] font-medium leading-tight text-brand-teal sm:text-[32px] sm:leading-[42px]">A11Y</span>
            <div className="flex items-center gap-1.5 text-[14px] leading-6 sm:text-[16px]">
              <span className="text-brand-green-80">Target :</span>
              <span className="hidden text-gray-40 sm:inline">{url || "https://samplesite.com/"}</span>
              <ExternalLink size={14} className="shrink-0 text-brand-green-80" />
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-6">
            <LanguageToggle />
            <DownloadCsvButton />
          </div>
        </header>

        <main className="flex flex-1 px-4 py-6 sm:px-8 sm:py-8 lg:px-16 lg:py-10">
          <div className="w-full rounded-[16px] bg-gray-10 px-4 py-6 flex flex-col gap-6 sm:px-10 sm:py-10">

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
          <DownloadCsvButton />
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

            {/* Max Depth + WCAG Level */}
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6">

              {/* Max Depth */}
              <div className="flex flex-1 flex-col gap-2">
                <label htmlFor="max-depth" className="text-[16px] leading-6 text-gray-100">
                  {t.newAudit.maxDepthLabel}
                </label>
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

            {/* Warning / notification box */}
            <div className="flex flex-col gap-6 rounded-[8px] bg-[#f6f1df] px-4 py-6">
              <div className="flex items-start gap-6">
                <AlertTriangle size={24} className="mt-0.5 shrink-0 text-[#f8c33d]" aria-hidden="true" />
                <p className="text-[16px] leading-6 text-gray-100">
                  {t.newAudit.warning}<br />
                  {t.newAudit.warningLine2}
                </p>
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
            </div>

            {/* Submit */}
            {error && (
              <p role="alert" className="text-[14px] leading-6 text-red-600">
                {error}
              </p>
            )}
            <button
              type="button"
              onClick={handleRun}
              disabled={submitting}
              className="flex w-full items-center justify-center gap-2 rounded-[16px] bg-brand-green-80 px-6 py-4 text-[16px] font-medium leading-6 text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <ArrowUp size={16} aria-hidden="true" />
              {submitting ? t.newAudit.submitting : t.newAudit.submit}
            </button>
          </div>

        </div>
      </main>
    </>
  );
}
