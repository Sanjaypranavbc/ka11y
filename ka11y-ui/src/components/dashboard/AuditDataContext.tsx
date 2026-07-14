"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import type { WcagAuditResponse } from "@/lib/wcagAudit";

const STORAGE_KEY = "kao:last-audit";

interface AuditDataContextValue {
  auditData: WcagAuditResponse | null;
  setAuditData: (data: WcagAuditResponse) => void;
}

const AuditDataContext = createContext<AuditDataContextValue | null>(null);

function readStoredAuditData(): WcagAuditResponse | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
}

export function AuditDataProvider({ children }: { children: ReactNode }) {
  const [auditData, setAuditDataState] = useState<WcagAuditResponse | null>(readStoredAuditData);

  function setAuditData(data: WcagAuditResponse) {
    setAuditDataState(data);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
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
