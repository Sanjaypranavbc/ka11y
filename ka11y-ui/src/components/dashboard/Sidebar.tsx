"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut, Plus, ChevronLeft, ChevronRight } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import {
  DashboardIcon,
  ViolationsIcon,
  NeedsReviewIcon,
  PassesIcon,
  SettingsNavIcon,
} from "@/components/ui/NavIcons";
import { DASHBOARD_NAV_ITEMS, isNavItemActive } from "@/lib/dashboardNav";
import { cn } from "@/lib/utils";

const NAV_ICON: Record<string, React.ComponentType<{ size?: number }>> = {
  dashboard: DashboardIcon,
  violations: ViolationsIcon,
  "needs-review": NeedsReviewIcon,
  passes: PassesIcon,
  settings: SettingsNavIcon,
};

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "relative sticky top-0 hidden h-screen shrink-0 flex-col bg-sidebar transition-[width] duration-200 md:flex",
        collapsed ? "w-20" : "w-[250px]",
      )}
    >
      {/* Logo row */}
      <div className="flex items-center justify-between px-6 py-6">
        {!collapsed && <Logo variant="color" />}
        <button
          type="button"
          onClick={() => setCollapsed((v) => !v)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-pressed={collapsed}
          className={cn(
            "inline-flex h-6 w-6 items-center justify-center rounded-full bg-white shadow-[0px_0px_6px_rgba(0,0,0,0.09)] text-gray-60 hover:text-brand-teal",
            collapsed && "mx-auto",
          )}
        >
          {collapsed ? (
            <ChevronRight size={12} aria-hidden="true" />
          ) : (
            <ChevronLeft size={12} aria-hidden="true" />
          )}
        </button>
      </div>

      {/* New Audit */}
      <div className="px-4">
        <Link
          href="/dashboard/new-audit"
          className={cn(
            "inline-flex w-full items-center justify-center gap-2 rounded-[12px] bg-brand-teal px-4 py-2.5 text-[14px] text-white hover:opacity-90",
            collapsed && "px-0",
          )}
        >
          <Plus size={16} aria-hidden="true" />
          {!collapsed && "New Audit"}
        </Link>
      </div>

      {/* Nav */}
      <nav aria-label="Dashboard" className="mt-5 flex-1 px-4">
        <ul className="flex flex-col gap-1">
          {DASHBOARD_NAV_ITEMS.map((item) => {
            const active = isNavItemActive(pathname, item.href);
            const Icon = NAV_ICON[item.iconName];
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2 rounded-[8px] py-2.5 pl-2 pr-14 text-[16px] leading-6 text-gray-80 hover:bg-gray-10",
                    active && "bg-brand-green-20 text-brand-teal-dark hover:bg-brand-green-20",
                    collapsed && "justify-center pr-0",
                  )}
                >
                  <Icon size={24} />
                  {!collapsed && item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Logout */}
      <div className="border-t border-gray-40 px-6 py-5">
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-2 text-[16px] leading-6 text-brand-green-80 hover:opacity-80",
            collapsed && "justify-center",
          )}
        >
          <LogOut size={16} aria-hidden="true" />
          {!collapsed && "Logout"}
        </button>
      </div>
    </aside>
  );
}
