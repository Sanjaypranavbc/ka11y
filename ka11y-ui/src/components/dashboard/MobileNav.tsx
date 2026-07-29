"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X, LogOut, Plus, Image as ImageVisualIcon } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { DashboardIcon, ViolationsIcon, NeedsReviewIcon, PassesIcon, SettingsNavIcon } from "@/components/ui/NavIcons";
import { DASHBOARD_NAV_ITEMS, isNavItemActive } from "@/lib/dashboardNav";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

const NAV_ICON: Record<string, React.ComponentType<{ size?: number }>> = {
  dashboard: DashboardIcon,
  violations: ViolationsIcon,
  "needs-review": NeedsReviewIcon,
  passes: PassesIcon,
  "image-visualisation": ImageVisualIcon,
  settings: SettingsNavIcon,
};

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const { t } = useLanguage();
  const NAV_LABEL: Record<string, string> = {
    dashboard: t.nav.dashboard,
    violations: t.nav.violations,
    "needs-review": t.nav.needsReview,
    passes: t.nav.passes,
    "image-visualisation": t.nav.imageVisualisation,
    settings: t.nav.settings,
  };

  return (
    <div className="flex items-center justify-between border-b border-gray-10 px-4 py-3 md:hidden">
      <Logo variant="color" />
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
                      onClick={() => setOpen(false)}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-3 text-p3 font-medium text-gray-60",
                        active && "bg-teal-10 text-brand-teal",
                      )}
                    >
                      <Icon size={18} aria-hidden="true" />
                      {NAV_LABEL[item.iconName]}
                    </Link>
                  </li>
                );
              })}
            </ul>
            </div>
            <button
              type="button"
              className="inline-flex items-center gap-2 px-3 py-3 text-p3 font-medium text-brand-teal"
            >
              <LogOut size={16} aria-hidden="true" />
              {t.nav.logout}
            </button>
          </nav>
        </div>
      )}
    </div>
  );
}
