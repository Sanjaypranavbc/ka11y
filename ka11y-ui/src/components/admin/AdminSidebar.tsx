"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { AdminBrand } from "@/components/admin/AdminBrand";
import { AdminNavList } from "@/components/admin/AdminNavList";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

interface AdminSidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function AdminSidebar({ collapsed, onToggle }: AdminSidebarProps) {
  const { t } = useLanguage();

  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-adm-border bg-white md:flex",
        "motion-safe:transition-[width] motion-safe:duration-200",
        collapsed ? "w-[72px]" : "w-[232px]",
      )}
    >
      <div className={cn("flex h-16 items-center border-b border-adm-border px-4", collapsed ? "justify-center" : "justify-between")}>
        {!collapsed && <AdminBrand />}
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-controls="admin-sidebar-nav"
          aria-label={collapsed ? t.admin.sidebar.expand : t.admin.sidebar.collapse}
          className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-gray-80 hover:bg-gray-10 hover:text-gray-100"
        >
          {collapsed ? <ChevronRight size={18} aria-hidden="true" /> : <ChevronLeft size={18} aria-hidden="true" />}
        </button>
      </div>

      <nav id="admin-sidebar-nav" aria-label={t.admin.navLabel} className="flex-1 overflow-y-auto px-3 py-5">
        <AdminNavList collapsed={collapsed} idPrefix="sidebar" />
      </nav>

      {!collapsed && (
        <div className="border-t border-adm-border px-5 py-5 text-center">
          <svg aria-hidden="true" viewBox="0 0 48 48" className="mx-auto mb-3 h-12 w-12" fill="none">
            <path d="M24 6c6 8 14 10 14 20a14 14 0 1 1-28 0c0-10 8-12 14-20Z" fill="var(--color-teal-40)" />
            <path d="M24 14c4 5 9 7 9 14a9 9 0 1 1-18 0c0-7 5-9 9-14Z" fill="var(--color-brand-teal)" />
          </svg>
          <p className="text-[14px] font-semibold leading-5 text-gray-100">{t.admin.consoleName}</p>
          <p className="mt-1 text-[13px] leading-5 text-gray-80">{t.admin.tagline}</p>
        </div>
      )}
    </aside>
  );
}
