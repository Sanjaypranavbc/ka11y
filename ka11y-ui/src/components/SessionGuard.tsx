"use client";

import { useEffect } from "react";
import { redirectToLogin } from "@/lib/auth";

/**
 * Re-validates the session whenever a gated page comes back into view
 * without a fresh request: restored from the back/forward cache after
 * logout, or a second tab that was open while another tab signed out.
 * A 401 from /auth/me ends up on the login page; anything else is left
 * alone (network hiccups must not log people out).
 */
export function SessionGuard() {
  useEffect(() => {
    let inFlight = false;
    const check = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await fetch("/api/v1/auth/me", { credentials: "same-origin", cache: "no-store" });
        if (res.status === 401) await redirectToLogin("signed_out");
      } catch {
        // Ignore: offline or API down.
      } finally {
        inFlight = false;
      }
    };
    const onPageShow = (e: PageTransitionEvent) => {
      if (e.persisted) void check();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") void check();
    };
    window.addEventListener("pageshow", onPageShow);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("pageshow", onPageShow);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
  return null;
}
