export interface DashboardNavItem {
  href: string;
  label: string;
  iconName: "dashboard" | "violations" | "needs-review" | "passes" | "settings";
}

export const DASHBOARD_NAV_ITEMS: DashboardNavItem[] = [
  { href: "/dashboard", label: "Dashboard", iconName: "dashboard" },
  { href: "/dashboard/violations", label: "Violations", iconName: "violations" },
  { href: "/dashboard/needs-review", label: "Needs Review", iconName: "needs-review" },
  { href: "/dashboard/passes", label: "Passes", iconName: "passes" },
  { href: "/dashboard/settings", label: "Settings", iconName: "settings" },
];

export function isNavItemActive(pathname: string, href: string) {
  return href === "/dashboard" ? pathname === href : pathname.startsWith(href);
}
