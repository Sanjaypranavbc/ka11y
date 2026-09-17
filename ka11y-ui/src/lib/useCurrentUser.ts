"use client";

import { useEffect, useState } from "react";

export type CurrentUser = {
  user_id: string | null;
  email: string | null;
  name: string | null;
  organization_id: string | null;
  role: string | null;
  anonymous: boolean;
  is_admin: boolean;
};

/**
 * The signed-in user as the API sees them (GET /api/v1/auth/me through the
 * same-origin rewrite). `null` until loaded or when not signed in. Used for
 * UI affordances only — every admin route is enforced server-side.
 */
export function useCurrentUser(): CurrentUser | null {
  const [user, setUser] = useState<CurrentUser | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/auth/me", { credentials: "same-origin", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return user;
}
