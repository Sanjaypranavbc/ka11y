import { useState, useCallback, useRef } from "react";
import { AuditConfig, AuditResult, StageInfo } from "@/types/audit";
import { emptyAuditResult } from "@/data/sampleData";

function mapPollResult(pollData: Record<string, unknown>, config: AuditConfig): AuditResult {
  const report = (pollData.result as Record<string, unknown>) || {};
  return {
    job_id: (pollData.job_id as string) || "",
    status: "completed",
    url: (report.url as string) || (pollData.url as string) || config.url,
    generated_at: (report.generated_at as string) || new Date().toISOString(),
    total:
      ((report.violations as unknown[])?.length || 0) +
      ((report.needs_review as unknown[])?.length || 0) +
      ((report.passes as unknown[])?.length || 0),
    violations_count: (report.violations as unknown[])?.length || 0,
    needs_review_count: (report.needs_review as unknown[])?.length || 0,
    passes_count: (report.passes as unknown[])?.length || 0,
    violations: (report.violations as AuditResult["violations"]) || [],
    needs_review: (report.needs_review as AuditResult["needs_review"]) || [],
    passes: (report.passes as AuditResult["passes"]) || [],
    warnings: (report.warnings as string[]) || (pollData.warnings as string[]) || [],
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

      es.addEventListener("stage_start", (e) => {
        const data = JSON.parse(e.data);
        setCurrentStage(data.stage_name);
        setStages((prev) => {
          if (prev.find((s) => s.name === data.stage_name)) return prev;
          return [
            ...prev,
            { name: data.stage_name, status: "running", started_at: data.started_at },
          ];
        });
      });

      es.addEventListener("stage_complete", (e) => {
        const data = JSON.parse(e.data);
        setStages((prev) =>
          prev.map((s) =>
            s.name === data.stage_name
              ? {
                  ...s,
                  status: "completed" as const,
                  completed_at: data.completed_at,
                  findings_count: data.findings_count,
                }
              : s,
          ),
        );
      });

      es.addEventListener("stage_error", (e) => {
        const data = JSON.parse(e.data);
        setStages((prev) =>
          prev.map((s) =>
            s.name === data.stage_name
              ? { ...s, status: "error" as const, error: data.error }
              : s,
          ),
        );
      });

      // Sent to late-connecting clients with current running state
      es.addEventListener("job_state", (e) => {
        const data = JSON.parse(e.data);
        if (data.current_stage) setCurrentStage(data.current_stage);
        if (data.stages?.length) setStages(data.stages);
      });

      es.addEventListener("job_complete", (e) => {
        const data = JSON.parse(e.data);
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
        const data = JSON.parse(e.data);
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
            run_ocr: config.run_ocr,
            run_image_audit: config.run_image_audit,
            run_form_audit: config.run_form_audit,
            run_label_in_name_audit: config.run_label_in_name_audit,
            run_pause_stop_hide_audit: config.run_pause_stop_hide_audit,
            run_target_size_audit: config.run_target_size_audit,
          }),
        });

        if (!res.ok) throw new Error(`API returned ${res.status}`);

        const data = await res.json();
        const jobId: string = data.job_id;
        jobIdRef.current = jobId;
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