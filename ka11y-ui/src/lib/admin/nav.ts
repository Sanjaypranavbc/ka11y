export type AdminNavKey =
  | "overview"
  | "audits"
  | "users"
  | "fails"
  | "reports"
  | "systemEvents"
  | "settings";

export interface AdminNavItem {
  key: AdminNavKey;
  href: string;
  section: "admin" | "system";
}

export const ADMIN_BASE = "/admin";

export const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  { key: "overview", href: "/admin", section: "admin" },
  { key: "audits", href: "/admin/audits", section: "admin" },
  { key: "users", href: "/admin/users", section: "admin" },
  { key: "fails", href: "/admin/fails", section: "admin" },
  { key: "reports", href: "/admin/reports", section: "admin" },
  { key: "systemEvents", href: "/admin/system-events", section: "admin" },
  { key: "settings", href: "/admin/settings", section: "system" },
];

export function isAdminNavActive(pathname: string, href: string) {
  return href === ADMIN_BASE ? pathname === href : pathname.startsWith(href);
}
