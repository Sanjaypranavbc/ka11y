import { useState, useCallback, useRef } from "react";
import { AuditConfig, AuditResult } from "@/types/audit";
import { sampleAuditResult } from "@/data/sampleData";

export function useAudit() {
  const [result, setResult] = useState<AuditResult>(sampleAuditResult);
  const [jobStatus, setJobStatus] = useState<"idle" | "pending" | "running" | "completed" | "failed">("idle");
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const runAudit = useCallback(async (config: AuditConfig) => {
    setJobStatus("pending");
    setError(null);
    stopPolling();

    try {
      const res = await fetch(`/api/v1/combined/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          url: config.url,
          max_depth: config.max_depth,
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
      const jobId = data.job_id;

      setJobStatus("running");

      pollingRef.current = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/v1/combined/${jobId}`, {
            headers: { Accept: "application/json" },
          });
          if (!pollRes.ok) throw new Error(`Poll returned ${pollRes.status}`);
          const pollData = await pollRes.json();

          if (pollData.status === "completed") {
            stopPolling();
            setJobStatus("completed");
            setResult({
              job_id: pollData.job_id || jobId,
              status: "completed",
              url: config.url,
              generated_at: pollData.generated_at || new Date().toISOString(),
              total: (pollData.violations?.length || 0) + (pollData.needs_review?.length || 0) + (pollData.passes?.length || 0),
              violations_count: pollData.violations?.length || 0,
              needs_review_count: pollData.needs_review?.length || 0,
              passes_count: pollData.passes?.length || 0,
              violations: pollData.violations || [],
              needs_review: pollData.needs_review || [],
              passes: pollData.passes || [],
            });
          } else if (pollData.status === "failed") {
            stopPolling();
            setJobStatus("failed");
            setError(pollData.error || "Audit failed");
          }
        } catch (e) {
          stopPolling();
          setJobStatus("failed");
          setError(e instanceof Error ? e.message : "Polling failed");
        }
      }, 3000);
    } catch (e) {
      setJobStatus("failed");
      setError(e instanceof Error ? e.message : "Failed to start audit");
    }
  }, [stopPolling]);

  const exportJSON = useCallback(() => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "combined_report.json";
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  return { result, jobStatus, error, runAudit, exportJSON };
}
