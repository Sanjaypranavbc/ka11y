import { Activity, AlertTriangle, ClipboardList, FileText, LayoutGrid, Settings, Users } from "lucide-react";
import type { AdminNavKey } from "@/lib/admin/nav";

const ICON: Record<AdminNavKey, React.ComponentType<{ size?: number; "aria-hidden"?: boolean | "true" }>> = {
  overview: LayoutGrid,
  audits: FileText,
  users: Users,
  fails: AlertTriangle,
  reports: ClipboardList,
  systemEvents: Activity,
  settings: Settings,
};

export function AdminNavIcon({ name, size = 20 }: { name: AdminNavKey; size?: number }) {
  const Icon = ICON[name];
  return <Icon size={size} aria-hidden="true" />;
}
