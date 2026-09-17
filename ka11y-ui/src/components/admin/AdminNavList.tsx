"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ADMIN_NAV_ITEMS, isAdminNavActive } from "@/lib/admin/nav";
import { AdminNavIcon } from "@/components/admin/AdminNavIcon";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

interface AdminNavListProps {
  collapsed?: boolean;
  onNavigate?: () => void;
  idPrefix: string;
}

/** The grouped nav used by both the desktop sidebar and the mobile dialog. */
export function AdminNavList({ collapsed = false, onNavigate, idPrefix }: AdminNavListProps) {
  const pathname = usePathname();
  const { t } = useLanguage();
  const sections: Array<"admin" | "system"> = ["admin", "system"];

  return (
    <div className="flex flex-col gap-6">
      {sections.map((section) => {
        const headingId = `${idPrefix}-${section}-heading`;
        return (
          <div key={section}>
            <h2
              id={headingId}
              className={cn(
                "mb-2 px-2 text-[12px] font-semibold uppercase leading-4 tracking-wider text-brand-teal-dark",
                collapsed && "sr-only",
              )}
            >
              {t.admin.sections[section]}
            </h2>
            <ul aria-labelledby={headingId} className="flex flex-col gap-1">
              {ADMIN_NAV_ITEMS.filter((item) => item.section === section).map((item) => {
                const active = isAdminNavActive(pathname, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      onClick={onNavigate}
                      className={cn(
                        "flex min-h-11 items-center gap-3 rounded-lg px-3 py-2 text-[15px] leading-5 text-gray-100 hover:bg-gray-10",
                        active && "bg-brand-green-20 font-medium text-brand-teal-dark hover:bg-brand-green-20",
                        collapsed && "justify-center px-0",
                      )}
                    >
                      <AdminNavIcon name={item.key} />
                      <span className={cn(collapsed && "sr-only")}>{t.admin.nav[item.key]}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
