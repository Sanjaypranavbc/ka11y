import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AdminShell } from "@/components/admin/AdminShell";
import { getServerUser } from "@/lib/serverAuth";

export const metadata: Metadata = {
  title: "Admin Console | A11Y",
  description: "Monitor, manage and run accessibility audits.",
};

// The user check runs per request; never pre-render this tree.
export const dynamic = "force-dynamic";

/**
 * /admin is only for the addresses on KA11Y_ADMIN_EMAILS (checked by the API
 * on every request via /auth/me → is_admin). Everyone else — signed in or
 * not — gets a 404 so the console is not advertised. proxy.ts already sends
 * cookie-less visitors to /login before this runs.
 */
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = await getServerUser();
  if (!user?.is_admin) notFound();
  return <AdminShell>{children}</AdminShell>;
}
