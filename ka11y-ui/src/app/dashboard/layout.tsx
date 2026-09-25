import type { Metadata } from "next";
import { DashboardShell } from "@/components/dashboard/DashboardShell";

export const metadata: Metadata = {
  title: "A11Y | kao",
  description: "Accessibility audit dashboard.",
};

// Gated area: render per request so the HTML is never served from a cache
// after the session has been ended.
export const dynamic = "force-dynamic";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  // AuditDataProvider / RunningAuditProvider are mounted in the root layout.
  return <DashboardShell>{children}</DashboardShell>;
}
