import { useState, useCallback, useRef, useEffect } from "react";
import { AuditConfig, AuditResult, ContrastReport, StageInfo } from "@/types/audit";
import { emptyAuditResult } from "@/data/sampleData";

// Backend returns element HTML nested as `element.html`; flatten it to `element_html` for the UI.
function flattenFinding(f: Record<string, unknown>) {
  const element = f.element as Record<string, unknown> | null | undefined;
  return {
    ...f,
    element_html: (element?.html as string) || "",
    element_tag: typeof element?.tag === "string" ? (element.tag as string) : null,
    element_id: typeof element?.element_id === "string" ? (element.element_id as string) : null,
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
  };
}

export function useAudit() {
  const [result, setResult] = useState<AuditResult>(emptyAuditResult);
  const [jobStatus, setJobStatus] = useState<
    "idle" | "pending" | "running" | "completed" | "failed"
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const [currentStage, setCurrentStage] = useState<string>("");
  const [stages, setStages] = useState<StageInfo[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);

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
          } else if (pollData.status === "failed") {
            stopPolling();
            setJobStatus("failed");
            setError(pollData.error || "Audit failed");
            setCurrentStage("");
          }
        } catch (e) {
          stopPolling();
          setJobStatus("failed");
          setError(e instanceof Error ? e.message : "Polling failed");
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

      es.addEventListener("stage_start", (e) => {
        const data = safeParse(e.data); if (!data) return;
        setCurrentStage(data.stage_name as string);
        setStages((prev) => {
          if (prev.find((s) => s.name === data.stage_name)) return prev;
          return [
            ...prev,
            { name: data.stage_name as string, status: "running", started_at: data.started_at as string },
          ];
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
          })
          .catch(() => setJobStatus("completed"));
      });

      es.addEventListener("job_failed", (e) => {
        const data = safeParse(e.data); if (!data) return;
        es.close();
        sseRef.current = null;
        stopPolling();
        setJobStatus("failed");
        setError(data.error || "Audit failed");
        setCurrentStage("");
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
      setCurrentStage("");
      setStages([]);
      setWarnings([]);
      stopPolling();
      closeSSE();
      configRef.current = config;

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

  return { result, jobStatus, error, runAudit, exportJSON, currentStage, stages, warnings };
}
