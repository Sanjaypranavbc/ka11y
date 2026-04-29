import { useState, useCallback, useRef, useEffect } from "react";
import {
  AuditConfig,
  AuditResult,
  ContrastReport,
  ImageAuditReport,
  JobFailure,
  JobPlan,
  StageInfo,
  StageProgressInfo,
} from "@/types/audit";
import { emptyAuditResult } from "@/data/sampleData";

const IMG_TEXT_RE = /<img-text\b[^>]*>([\s\S]*?)<\/img-text>/i;
const IMG_SRC_RE = /<img\b[^>]*\bsrc=(["'])(.*?)\1/i;
const IMAGE_REASON_RE = /\bimage "([^"]+)"/i;
const IMAGE_FILE_RE = /([A-Za-z0-9._-]+\.(?:png|jpe?g|gif|webp|svg|avif))/i;

function normalizeImageReference(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const withoutQuery = trimmed.split("?")[0].split("#")[0];
  const parts = withoutQuery.split("/").filter(Boolean);
  return parts[parts.length - 1] || withoutQuery;
}

function extractImageText(html: string): string | null {
  const match = html.match(IMG_TEXT_RE);
  if (!match) return null;
  const text = match[1].replace(/\s+/g, " ").trim();
  return text || null;
}

function extractImageSrc(html: string): string | null {
  const match = html.match(IMG_SRC_RE);
  return match?.[2]?.trim() || null;
}

function inferImageReference(
  reason: string,
  imageSrc: string | null,
  elementId: unknown,
): string | null {
  const quoted = reason.match(IMAGE_REASON_RE)?.[1];
  if (quoted) return normalizeImageReference(quoted);

  if (typeof elementId === "string" && IMAGE_FILE_RE.test(elementId)) {
    return normalizeImageReference(elementId);
  }

  if (imageSrc) {
    return normalizeImageReference(imageSrc);
  }

  const fileLike = reason.match(IMAGE_FILE_RE)?.[1];
  return fileLike ? normalizeImageReference(fileLike) : null;
}

// Backend returns element HTML nested as `element.html`; flatten it to `element_html` for the UI.
function flattenFinding(f: Record<string, unknown>) {
  const directElement = f.element as Record<string, unknown> | null | undefined;
  const firstListElement = Array.isArray(f.elements)
    ? (f.elements.find((e) => !!e && typeof e === "object") as Record<string, unknown> | undefined)
    : undefined;
  const element = (directElement && typeof directElement === "object")
    ? directElement
    : firstListElement;

  const explicitHtml = typeof f.element_html === "string"
    ? (f.element_html as string)
    : (typeof f.html_snippet === "string" ? (f.html_snippet as string) : "");
  const htmlFromElement = typeof element?.html === "string" ? (element.html as string) : "";
  const tagFromElement = element?.tag ?? element?.tagName;
  const idFromElement = element?.element_id ?? element?.id;
  const targetFromElement = Array.isArray(element?.target) ? element?.target : [];
  const reason = typeof f.reason === "string" ? (f.reason as string) : "";
  const selectorFromElement =
    (typeof element?.selector === "string" ? (element.selector as string) : null) ||
    (typeof f.element_selector === "string" ? (f.element_selector as string) : null) ||
    (typeof f.selector === "string" ? (f.selector as string) : null) ||
    (typeof targetFromElement?.[0] === "string" ? (targetFromElement[0] as string) : null);
  const elementHtml = explicitHtml || htmlFromElement || "";
  const imageText = (typeof element?.image_text === "string" ? element.image_text : null) || extractImageText(elementHtml);
  const imageSrc = (typeof element?.image_src === "string" ? element.image_src : null) || extractImageSrc(elementHtml);
  const imageReference = (typeof element?.image_reference === "string" ? element.image_reference : null) || inferImageReference(reason, imageSrc, idFromElement);

  return {
    ...f,
    element_html: elementHtml,
    element_tag: typeof tagFromElement === "string" ? (tagFromElement as string) : null,
    element_id: typeof idFromElement === "string" ? (idFromElement as string) : null,
    element_selector: selectorFromElement,
    image_reference: imageReference,
    image_src: imageSrc,
    image_text: imageText,
  };
}

function mapPollResult(pollData: Record<string, unknown>, config: AuditConfig): AuditResult {
  const report = (pollData.result as Record<string, unknown>) || {};
  const rawViolations = (report.violations as Record<string, unknown>[]) || [];
  const rawNeedsReview = (report.needs_review as Record<string, unknown>[]) || [];
  return {
    job_id: (pollData.job_id as string) || "",
    status: "completed",
    url: (report.url as string) || (pollData.url as string) || config.url,
    generated_at: (report.generated_at as string) || new Date().toISOString(),
    lang: (report.lang as string) || (pollData.lang as string) || config.lang,
    total:
      rawViolations.length + rawNeedsReview.length +
      ((report.passes as unknown[])?.length || 0),
    violations_count: rawViolations.length,
    needs_review_count: rawNeedsReview.length,
    passes_count: (report.passes as unknown[])?.length || 0,
    violations: rawViolations.map(flattenFinding) as AuditResult["violations"],
    needs_review: rawNeedsReview.map(flattenFinding) as AuditResult["needs_review"],
    passes: (((report.passes as Record<string, unknown>[]) || []).map(flattenFinding) as AuditResult["passes"]) || [],
    warnings: (report.warnings as string[]) || (pollData.warnings as string[]) || [],
    contrast_report: (report.contrast_report as ContrastReport) ?? null,
    image_audit_report: (report.image_audit_report as ImageAuditReport) ?? null,
  };
}

export function useAudit() {
  const [result, setResult] = useState<AuditResult>(emptyAuditResult);
  const [jobStatus, setJobStatus] = useState<
    "idle" | "pending" | "running" | "completed" | "failed"
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<JobFailure | null>(null);
  const [currentStage, setCurrentStage] = useState<string>("");
  const [stages, setStages] = useState<StageInfo[]>([]);
  const [plan, setPlan] = useState<JobPlan | null>(null);
  const [stageProgress, setStageProgress] = useState<StageProgressInfo | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [activeRun, setActiveRun] = useState<{ url: string; lang: string; submitted_at: string } | null>(null);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sseRef = useRef<EventSource | null>(null);
  const jobIdRef = useRef<string>("");
  const configRef = useRef<AuditConfig | null>(null);
  const activeJobRef = useRef<string>("");  // tracks current job — stale polls ignore old job ids

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const closeSSE = useCallback(() => {
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }
  }, []);

  // ── Polling fallback ──────────────────────────────────────────────────────
  const startPollingFallback = useCallback(
    (jobId: string, config: AuditConfig) => {
      if (pollingRef.current) return; // already polling
      pollingRef.current = setInterval(async () => {
        // Stale poll guard — discard results if a newer job has since been submitted
        if (activeJobRef.current !== jobId) { stopPolling(); return; }
        try {
          const pollRes = await fetch(`/api/v1/combined/${jobId}`, {
            headers: { Accept: "application/json" },
          });
          if (!pollRes.ok) throw new Error(`Poll returned ${pollRes.status}`);
          const pollData = await pollRes.json();

          // Sync stage info from job state
          if (pollData.current_stage) setCurrentStage(pollData.current_stage);
          if (pollData.stages?.length) setStages(pollData.stages);

          if (pollData.status === "completed") {
            stopPolling();
            setResult(mapPollResult(pollData, config));
            setWarnings(pollData.warnings || []);
            setJobStatus("completed");
            setCurrentStage("");
            setActiveRun(null);
          } else if (pollData.status === "failed") {
            stopPolling();
            setJobStatus("failed");
            setError(pollData.error || "Audit failed");
            setCurrentStage("");
            setActiveRun(null);
          }
        } catch (e) {
          stopPolling();
          setJobStatus("failed");
          setError(e instanceof Error ? e.message : "Polling failed");
          setActiveRun(null);
        }
      }, 3000);
    },
    [stopPolling],
  );

  // ── SSE connection ────────────────────────────────────────────────────────
  const connectSSE = useCallback(
    (jobId: string, config: AuditConfig) => {
      closeSSE();

      const es = new EventSource(`/api/v1/combined/${jobId}/stream`);
      sseRef.current = es;

      function safeParse(raw: string): Record<string, unknown> | null {
        try { return JSON.parse(raw) as Record<string, unknown>; }
        catch { return null; }
      }

      es.addEventListener("job_plan", (e) => {
        const data = safeParse(e.data); if (!data) return;
        setPlan({
          stages: (data.stages as JobPlan["stages"]) || [],
          total: (data.total as number) || 0,
          weight_total: (data.weight_total as number) || 1,
          started_at: (data.started_at as string) || new Date().toISOString(),
        });
      });

      es.addEventListener("stage_start", (e) => {
        const data = safeParse(e.data); if (!data) return;
        setCurrentStage(data.stage_name as string);
        setStageProgress(null);
        setStages((prev) => {
          const existing = prev.find((s) => s.name === data.stage_name);
          if (existing) return prev;
          return [
            ...prev,
            {
              name: data.stage_name as string,
              status: "running",
              started_at: data.started_at as string,
              index: data.index as number | undefined,
              total: data.total as number | undefined,
              weight: data.weight as number | undefined,
            },
          ];
        });
      });

      es.addEventListener("stage_progress", (e) => {
        const data = safeParse(e.data); if (!data) return;
        setStageProgress({
          stage_name: data.stage_name as string,
          current: data.current as number,
          total: data.total as number,
          phase: data.phase as string | undefined,
        });
      });

      es.addEventListener("stage_complete", (e) => {
        const data = safeParse(e.data); if (!data) return;
        setStages((prev) =>
          prev.map((s) =>
            s.name === data.stage_name
              ? {
                  ...s,
                  status: "completed" as const,
                  completed_at: data.completed_at as string,
                  findings_count: data.findings_count as number,
                }
              : s,
          ),
        );
        // Clear inner progress when the owning stage completes.
        setStageProgress((p) => (p && p.stage_name === data.stage_name ? null : p));
      });

      es.addEventListener("stage_error", (e) => {
        const data = safeParse(e.data); if (!data) return;
        setStages((prev) =>
          prev.map((s) =>
            s.name === data.stage_name
              ? { ...s, status: "error" as const, error: data.error as string }
              : s,
          ),
        );
        setStageProgress((p) => (p && p.stage_name === data.stage_name ? null : p));
      });

      // Sent to late-connecting clients with current running state
      es.addEventListener("job_state", (e) => {
        const data = safeParse(e.data); if (!data) return;
        if (data.current_stage) setCurrentStage(data.current_stage as string);
        if ((data.stages as unknown[])?.length) setStages(data.stages as StageInfo[]);
      });

      es.addEventListener("job_complete", (e) => {
        const data = safeParse(e.data); if (!data) return;
        es.close();
        sseRef.current = null;
        stopPolling();
        setCurrentStage("");
        // Fetch full result — SSE summary is lightweight
        fetch(`/api/v1/combined/${data.job_id}`, {
          headers: { Accept: "application/json" },
        })
          .then((r) => r.json())
          .then((pollData) => {
            setResult(mapPollResult(pollData, config));
            setWarnings(pollData.warnings || []);
            setJobStatus("completed");
            setActiveRun(null);
          })
          .catch(() => {
            setJobStatus("completed");
            setActiveRun(null);
          });
      });

      es.addEventListener("job_failed", (e) => {
        const data = safeParse(e.data); if (!data) return;
        es.close();
        sseRef.current = null;
        stopPolling();
        setJobStatus("failed");
        const errStr = (data.error as string) || "Audit failed";
        setError(errStr);
        setFailure({
          error: errStr,
          stage: data.stage as string | undefined,
          location: data.location as string | undefined,
          traceback: data.traceback as string | undefined,
        });
        setCurrentStage("");
        setStageProgress(null);
        setActiveRun(null);
      });

      es.onerror = () => {
        // Only handle if this SSE instance is still active
        if (sseRef.current !== es) return;
        es.close();
        sseRef.current = null;
        // Fall back to polling
        if (jobIdRef.current && configRef.current) {
          startPollingFallback(jobIdRef.current, configRef.current);
        }
      };
    },
    [closeSSE, stopPolling, startPollingFallback],
  );

  // ── Run audit ─────────────────────────────────────────────────────────────
  const runAudit = useCallback(
    async (config: AuditConfig) => {
      setJobStatus("pending");
      setError(null);
      setFailure(null);
      setCurrentStage("");
      setStages([]);
      setPlan(null);
      setStageProgress(null);
      setWarnings([]);
      stopPolling();
      closeSSE();
      configRef.current = config;
      setActiveRun({
        url: config.url,
        lang: config.lang,
        submitted_at: new Date().toISOString(),
      });

      try {
        const res = await fetch(`/api/v1/combined/`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            url: config.url,
            max_depth: config.max_depth,
            wcag_level: config.wcag_level,
            lang: config.lang ?? "en",
            run_ocr: config.run_ocr,
            run_image_audit: config.run_image_audit,
            run_form_audit: config.run_form_audit,
            run_label_in_name_audit: config.run_label_in_name_audit,
            run_pause_stop_hide_audit: config.run_pause_stop_hide_audit,
            run_target_size_audit: config.run_target_size_audit,
            run_resize_text_audit: config.run_resize_text_audit,
            run_reflow_audit: config.run_reflow_audit,
            run_text_spacing_audit: config.run_text_spacing_audit,
            run_orientation_audit: config.run_orientation_audit,
            run_hover_focus_content_audit: config.run_hover_focus_content_audit,
            run_focus_not_obscured_min_audit: config.run_focus_not_obscured_min_audit,
            run_focus_not_obscured_enh_audit: config.run_focus_not_obscured_enh_audit,
            run_media_audit: config.run_media_audit,
            run_captions_audit: config.run_captions_audit,
            run_sensory_audit: config.run_sensory_audit,
          }),
        });

        if (!res.ok) throw new Error(`API returned ${res.status}`);

        const data = await res.json();
        const jobId: string = data.job_id;
        jobIdRef.current = jobId;
        activeJobRef.current = jobId;
        setJobStatus("running");

        // Connect SSE for real-time events; onerror falls back to polling
        connectSSE(jobId, config);
      } catch (e) {
        setJobStatus("failed");
        setError(e instanceof Error ? e.message : "Failed to start audit");
        setActiveRun(null);
      }
    },
    [stopPolling, closeSSE, connectSSE],
  );

  // ── Cleanup on unmount ────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      stopPolling();
      closeSSE();
    };
  }, [stopPolling, closeSSE]);

  // ── Export ────────────────────────────────────────────────────────────────
  const exportJSON = useCallback(() => {
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "combined_report.json";
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  return {
    result,
    jobStatus,
    error,
    failure,
    runAudit,
    exportJSON,
    currentStage,
    stages,
    plan,
    stageProgress,
    warnings,
    activeRun,
  };
}

