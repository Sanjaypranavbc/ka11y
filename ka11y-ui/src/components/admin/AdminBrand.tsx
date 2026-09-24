"use client";

import { Logo } from "@/components/ui/Logo";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { POST_LOGIN_PATH } from "@/lib/auth";
import { cn } from "@/lib/utils";

/** Kao logo (a link to New Audit) + the A11Y wordmark, used by the sidebar and the mobile header. */
export function AdminBrand({ className, wordmark = true }: { className?: string; wordmark?: boolean }) {
  const { t } = useLanguage();
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <Logo variant="color" href={POST_LOGIN_PATH} label={t.nav.homeLink} />
      {wordmark && (
        <span
          className="border-l border-gray-40 pl-3 text-[20px] font-semibold leading-6 tracking-wide text-brand-teal-dark"
          style={{ fontFamily: "var(--font-logo), var(--font-sans)" }}
        >
          A11Y
        </span>
      )}
    </div>
  );
}
