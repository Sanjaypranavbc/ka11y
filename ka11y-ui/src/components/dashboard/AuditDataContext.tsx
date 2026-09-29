"use client";

import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import type { WcagAuditResponse } from "@/lib/wcagAudit";

const STORAGE_KEY = "kao:last-audit";
const JOB_STORAGE_KEY = "kao:last-audit-job";

interface AuditDataContextValue {
  auditData: WcagAuditResponse | null;
  /** Backend job id of `auditData`; drives the report export links. Null for
   * a result restored from an older session that did not record it. */
  jobId: string | null;
  setAuditData: (data: WcagAuditResponse, jobId?: string | null) => void;
}

const AuditDataContext = createContext<AuditDataContextValue | null>(null);

export function AuditDataProvider({ children }: { children: ReactNode }) {
  const [auditData, setAuditDataState] = useState<WcagAuditResponse | null>(null);
  const [jobId, setJobIdState] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored) {
        setAuditDataState(JSON.parse(stored));
        setJobIdState(sessionStorage.getItem(JOB_STORAGE_KEY));
      }
    } catch {
      // sessionStorage unavailable or parse error
    }
  }, []);

  function setAuditData(data: WcagAuditResponse, nextJobId: string | null = null) {
    setAuditDataState(data);
    setJobIdState(nextJobId);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      if (nextJobId) sessionStorage.setItem(JOB_STORAGE_KEY, nextJobId);
      else sessionStorage.removeItem(JOB_STORAGE_KEY);
    } catch {
      // sessionStorage unavailable
    }
  }

  return (
    <AuditDataContext.Provider value={{ auditData, jobId, setAuditData }}>
      {children}
    </AuditDataContext.Provider>
  );
}

export function useAuditData() {
  const ctx = useContext(AuditDataContext);
  if (!ctx) throw new Error("useAuditData must be used within an AuditDataProvider");
  return ctx;
}
