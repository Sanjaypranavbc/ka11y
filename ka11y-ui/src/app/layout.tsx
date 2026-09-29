import type { Metadata } from "next";
import { Baloo_2, Inter } from "next/font/google";
import { LanguageProvider } from "@/components/dashboard/LanguageContext";
import { AuditDataProvider } from "@/components/dashboard/AuditDataContext";
import { AuditLockGuard, RunningAuditProvider } from "@/components/dashboard/RunningAuditContext";
import "./globals.css";

const baloo2 = Baloo_2({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-logo",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "kao",
  description: "kao product experience, built on the brand design system.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${baloo2.variable} ${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans">
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        {/* Audit result + running-audit state live above both the dashboard
            and the admin console: an audit keeps polling (and keeps the other
            screens locked) wherever the user navigates. */}
        <LanguageProvider>
          <AuditDataProvider>
            <RunningAuditProvider>
              <AuditLockGuard />
              {children}
            </RunningAuditProvider>
          </AuditDataProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
