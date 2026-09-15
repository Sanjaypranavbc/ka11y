"use client";

import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import type { WcagAuditResponse } from "@/lib/wcagAudit";

const STORAGE_KEY = "kao:last-audit";

interface AuditDataContextValue {
  auditData: WcagAuditResponse | null;
  setAuditData: (data: WcagAuditResponse) => void;
}

const AuditDataContext = createContext<AuditDataContextValue | null>(null);

export function AuditDataProvider({ children }: { children: ReactNode }) {
  const [auditData, setAuditDataState] = useState<WcagAuditResponse | null>(null);

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored) {
        setAuditDataState(JSON.parse(stored));
      }
    } catch {
      // sessionStorage unavailable or parse error
    }
  }, []);

  function setAuditData(data: WcagAuditResponse) {
    setAuditDataState(data);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      // sessionStorage unavailable
    }
  }

  return (
    <AuditDataContext.Provider value={{ auditData, setAuditData }}>
      {children}
    </AuditDataContext.Provider>
  );
}

export function useAuditData() {
  const ctx = useContext(AuditDataContext);
  if (!ctx) throw new Error("useAuditData must be used within an AuditDataProvider");
  return ctx;
}
