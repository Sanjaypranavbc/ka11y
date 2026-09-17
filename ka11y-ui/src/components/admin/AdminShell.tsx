"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import type { AdminOverviewData, AuditJob } from "@/lib/admin/data";
import { loadAdminOverview, loadAuditDetail, subscribeAdminEvents } from "@/lib/admin/api";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { AdminMobileNav } from "@/components/admin/AdminMobileNav";
import { AdminTopBar } from "@/components/admin/AdminTopBar";
import { AuditDetailsDrawer } from "@/components/admin/AuditDetailsDrawer";

type LoadState = "loading" | "ready" | "error";

interface AdminConsoleContextValue {
  data: AdminOverviewData | null;
  status: LoadState;
  reload: () => void;
  /** Opens the Audit Details drawer for `job`; pages/fails/log load lazily. */
  openAudit: (job: AuditJob) => void;
  closeAudit: () => void;
  selectedJob: AuditJob | null;
  /** True while the Server-Sent Events change feed is connected. */
  live: boolean;
  /** Increments on every change notification; pages refetch when it moves. */
  version: number;
  updatedAt: string | null;
}

const AdminConsoleContext = createContext<AdminConsoleContextValue | null>(null);

export function useAdminConsole() {
  const ctx = useContext(AdminConsoleContext);
  if (!ctx) throw new Error("useAdminConsole must be used within AdminShell");
  return ctx;
}

const POLL_MS = 30_000; // fallback while the event stream is down
const MIN_REFRESH_GAP_MS = 1_500; // coalesce bursts of change events

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [selectedJob, setSelectedJob] = useState<AuditJob | null>(null);
  const [data, setData] = useState<AdminOverviewData | null>(null);
  const [status, setStatus] = useState<LoadState>("loading");
  const [version, setVersion] = useState(0);
  const [live, setLive] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const lastRefresh = useRef(0);
  const pending = useRef<number | null>(null);

  // Route change closes any overlay so focus is not stranded in a dialog.
  const [lastPathname, setLastPathname] = useState(pathname);
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setMobileOpen(false);
    setSelectedJob(null);
  }

  function toggleSidebar() {
    setCollapsed((v) => !v);
  }

  // (Re)load the overview whenever `version` moves. The first load shows the
  // loading state; later ones are silent so the page never flickers.
  useEffect(() => {
    let cancelled = false;
    loadAdminOverview()
      .then((next) => {
        if (cancelled) return;
        setData(next);
        setUpdatedAt(next.generatedAt);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus((s) => (s === "ready" ? s : "error"));
      });
    return () => {
      cancelled = true;
    };
  }, [version]);

  const bump = useCallback(() => {
    const now = Date.now();
    const wait = Math.max(0, MIN_REFRESH_GAP_MS - (now - lastRefresh.current));
    if (pending.current !== null) return;
    pending.current = window.setTimeout(() => {
      pending.current = null;
      lastRefresh.current = Date.now();
      setVersion((n) => n + 1);
    }, wait);
  }, []);

  // Live feed: the API pushes `refresh` whenever its tables change.
  useEffect(() => {
    const unsubscribe = subscribeAdminEvents(bump, setLive);
    return () => {
      unsubscribe();
      if (pending.current !== null) window.clearTimeout(pending.current);
    };
  }, [bump]);

  // Fallback polling only while the stream is not connected.
  useEffect(() => {
    if (live) return;
    const id = window.setInterval(bump, POLL_MS);
    return () => window.clearInterval(id);
  }, [live, bump]);

  const reload = useCallback(() => {
    setStatus("loading");
    setVersion((n) => n + 1);
  }, []);

  const openAudit = useCallback((job: AuditJob) => {
    setSelectedJob(job);
    loadAuditDetail(job.id)
      .then((detail) => {
        setSelectedJob((current) => (current && current.id === detail.id ? { ...current, ...detail } : current));
      })
      .catch(() => {
        // The drawer still shows the summary row; detail tabs stay empty.
      });
  }, []);
  const closeAudit = useCallback(() => setSelectedJob(null), []);

  const value = useMemo<AdminConsoleContextValue>(
    () => ({ data, status, reload, openAudit, closeAudit, selectedJob, live, version, updatedAt }),
    [data, status, reload, openAudit, closeAudit, selectedJob, live, version, updatedAt],
  );

  const overlayOpen = mobileOpen || selectedJob !== null;

  return (
    <AdminConsoleContext.Provider value={value}>
      <div className="admin-root min-h-screen bg-gray-10 text-gray-100">
        {/* `inert` hides the page from pointer, keyboard and assistive tech while a dialog is open (WCAG 2.4.3). */}
        <div inert={overlayOpen || undefined} className="flex min-h-screen">
          <AdminSidebar collapsed={collapsed} onToggle={toggleSidebar} />
          <div className="flex min-h-screen min-w-0 flex-1 flex-col">
            <AdminTopBar
              user={data?.currentUser ?? null}
              notifications={data?.notifications ?? []}
              onOpenMobileNav={() => setMobileOpen(true)}
            />
            <main id="main-content" tabIndex={-1} className="flex-1 px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
              {children}
            </main>
          </div>
        </div>
        <AdminMobileNav open={mobileOpen} onClose={() => setMobileOpen(false)} />
        <AuditDetailsDrawer job={selectedJob} onClose={closeAudit} />
      </div>
    </AdminConsoleContext.Provider>
  );
}
