import type { Metadata } from "next";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { AuditDataProvider } from "@/components/dashboard/AuditDataContext";
import { LanguageProvider } from "@/components/dashboard/LanguageContext";

export const metadata: Metadata = {
  title: "A11Y | kao",
  description: "Accessibility audit dashboard.",
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      <AuditDataProvider>
        <DashboardShell>{children}</DashboardShell>
      </AuditDataProvider>
    </LanguageProvider>
  );
}
