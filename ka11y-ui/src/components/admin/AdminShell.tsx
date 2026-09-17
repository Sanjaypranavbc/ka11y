"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import type { AdminOverviewData, AuditJob } from "@/lib/admin/data";
import { loadAdminOverview } from "@/lib/admin/data";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { AdminMobileNav } from "@/components/admin/AdminMobileNav";
import { AdminTopBar } from "@/components/admin/AdminTopBar";
import { AuditDetailsDrawer } from "@/components/admin/AuditDetailsDrawer";

type LoadState = "loading" | "ready" | "error";

interface AdminConsoleContextValue {
  data: AdminOverviewData | null;
  status: LoadState;
  reload: () => void;
  /** Opens the Audit Details drawer for `job`. Focus returns to the invoker on close. */
  openAudit: (job: AuditJob) => void;
  closeAudit: () => void;
  selectedJob: AuditJob | null;
}

const AdminConsoleContext = createContext<AdminConsoleContextValue | null>(null);

export function useAdminConsole() {
  const ctx = useContext(AdminConsoleContext);
  if (!ctx) throw new Error("useAdminConsole must be used within AdminShell");
  return ctx;
}

const REFRESH_MS = 30_000;

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [selectedJob, setSelectedJob] = useState<AuditJob | null>(null);
  const [data, setData] = useState<AdminOverviewData | null>(null);
  const [status, setStatus] = useState<LoadState>("loading");
  const [tick, setTick] = useState(0);

  // Route change closes any overlay so focus is not stranded in a dialog.
  // State is adjusted during render (the React-sanctioned pattern) rather
  // than in an effect, which would paint one frame with the stale overlay.
  const [lastPathname, setLastPathname] = useState(pathname);
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setMobileOpen(false);
    setSelectedJob(null);
  }

  function toggleSidebar() {
    setCollapsed((v) => !v);
  }

  useEffect(() => {
    let cancelled = false;
    loadAdminOverview()
      .then((next) => {
        if (cancelled) return;
        setData(next);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  // Background refresh keeps the feed and counters current without a reload.
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), REFRESH_MS);
    return () => window.clearInterval(id);
  }, []);

  const reload = useCallback(() => {
    setStatus("loading");
    setTick((n) => n + 1);
  }, []);
  const openAudit = useCallback((job: AuditJob) => setSelectedJob(job), []);
  const closeAudit = useCallback(() => setSelectedJob(null), []);

  const value = useMemo<AdminConsoleContextValue>(
    () => ({ data, status, reload, openAudit, closeAudit, selectedJob }),
    [data, status, reload, openAudit, closeAudit, selectedJob],
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
