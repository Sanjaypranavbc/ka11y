"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X, LogOut, Plus, ShieldCheck } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { POST_LOGIN_PATH } from "@/lib/auth";
import { DashboardIcon, ViolationsIcon, NeedsReviewIcon, PassesIcon, SettingsNavIcon } from "@/components/ui/NavIcons";
import { DASHBOARD_NAV_ITEMS, isNavItemActive } from "@/lib/dashboardNav";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";
import { LOGOUT_URL } from "@/lib/auth";
import { useCurrentUser } from "@/lib/useCurrentUser";
import { useRunningAudit } from "@/components/dashboard/RunningAuditContext";
import { RUNNING_AUDIT_PATH } from "@/lib/runningAudit";

const NAV_ICON: Record<string, React.ComponentType<{ size?: number }>> = {
  dashboard: DashboardIcon,
  violations: ViolationsIcon,
  "needs-review": NeedsReviewIcon,
  passes: PassesIcon,
  settings: SettingsNavIcon,
};

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const { t } = useLanguage();
  const me = useCurrentUser();
  const { isLocked } = useRunningAudit();
  const lockedProps = (href: string) =>
    isLocked && href !== RUNNING_AUDIT_PATH
      ? {
          "aria-disabled": true as const,
          tabIndex: -1,
          title: t.nav.lockedHint,
          onClick: (e: React.MouseEvent) => e.preventDefault(),
        }
      : { onClick: () => setOpen(false) };
  const NAV_LABEL: Record<string, string> = {
    dashboard: t.nav.dashboard,
    violations: t.nav.violations,
    "needs-review": t.nav.needsReview,
    passes: t.nav.passes,
    settings: t.nav.settings,
  };

  return (
    <div className="flex items-center justify-between border-b border-gray-10 px-4 py-3 md:hidden">
      <Logo variant="color" href={POST_LOGIN_PATH} label={t.nav.homeLink} />
      <button
        type="button"
        aria-expanded={open}
        aria-controls="dashboard-mobile-nav"
        aria-label={open ? t.nav.closeMenu : t.nav.openMenu}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-9 w-9 items-center justify-center rounded-md text-brand-gray"
      >
        {open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
      </button>

      {open && (
        <div
          id="dashboard-mobile-nav"
          className="fixed inset-0 top-[57px] z-40 bg-background"
        >
          <nav aria-label={t.nav.dashboardNavLabel} className="flex h-full flex-col justify-between px-4 py-6">
            <div className="flex flex-col gap-4">
              <Link
                href="/dashboard/new-audit"
                onClick={() => setOpen(false)}
                className="inline-flex w-full items-center justify-center gap-2 rounded-[12px] bg-brand-teal px-4 py-2.5 text-[14px] text-white hover:opacity-90"
              >
                <Plus size={16} aria-hidden="true" />
                {t.nav.newAudit}
              </Link>
            <ul className="flex flex-col gap-1">
              {DASHBOARD_NAV_ITEMS.map((item) => {
                const active = isNavItemActive(pathname, item.href);
                const Icon = NAV_ICON[item.iconName];
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      {...lockedProps(item.href)}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-3 text-p3 font-medium text-gray-60",
                        active && "bg-teal-10 text-brand-teal",
                        isLocked && "cursor-not-allowed opacity-40",
                      )}
                    >
                      <Icon size={18} aria-hidden="true" />
                      {NAV_LABEL[item.iconName]}
                    </Link>
                  </li>
                );
              })}
            </ul>
            {isLocked && (
              <p role="status" className="px-3 text-[13px] leading-5 text-gray-80">
                {t.nav.lockedHint}
              </p>
            )}
            {me?.is_admin && (
              <ul className="mt-3 border-t border-gray-40 pt-3">
                <li>
                  <Link
                    href="/admin"
                    {...lockedProps("/admin")}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-3 text-p3 font-medium text-gray-60",
                      isLocked && "cursor-not-allowed opacity-40",
                    )}
                  >
                    <ShieldCheck size={18} aria-hidden="true" />
                    {t.nav.adminConsole}
                  </Link>
                </li>
              </ul>
            )}
            </div>
            <a
              href={LOGOUT_URL}
              className="inline-flex items-center gap-2 px-3 py-3 text-p3 font-medium text-brand-teal"
            >
              <LogOut size={16} aria-hidden="true" />
              {t.nav.logout}
            </a>
          </nav>
        </div>
      )}
    </div>
  );
}
