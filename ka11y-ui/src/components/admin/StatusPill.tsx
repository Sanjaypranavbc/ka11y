"use client";

import { Ban, CircleAlert, CircleCheck, CircleX, Clock, LoaderCircle } from "lucide-react";
import type { AuditStatus } from "@/lib/admin/data";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

type PillStatus = AuditStatus | "passed";

const STYLE: Record<PillStatus, string> = {
  completed: "bg-adm-completed-bg text-adm-completed",
  passed: "bg-adm-completed-bg text-adm-completed",
  running: "bg-adm-running-bg text-adm-running",
  failed: "bg-adm-failed-bg text-adm-failed",
  needsReview: "bg-adm-review-bg text-adm-review",
  cancelled: "bg-adm-cancelled-bg text-adm-cancelled",
  queued: "bg-adm-cancelled-bg text-adm-cancelled",
};

const ICON: Record<PillStatus, React.ComponentType<{ size?: number; className?: string; "aria-hidden"?: boolean | "true" }>> = {
  completed: CircleCheck,
  passed: CircleCheck,
  running: LoaderCircle,
  failed: CircleX,
  needsReview: CircleAlert,
  cancelled: Ban,
  queued: Clock,
};

interface StatusPillProps {
  status: PillStatus;
  className?: string;
  size?: "sm" | "md";
}

/**
 * Status = icon + colour + text, so colour is never the only signal
 * (WCAG 1.4.1). The label comes from the active language.
 */
export function StatusPill({ status, className, size = "sm" }: StatusPillProps) {
  const { t } = useLanguage();
  const Icon = ICON[status];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full font-medium",
        size === "sm" ? "px-2.5 py-1 text-[13px] leading-4" : "px-3 py-1.5 text-[14px] leading-5",
        STYLE[status],
        className,
      )}
    >
      <Icon
        size={size === "sm" ? 14 : 16}
        aria-hidden="true"
        className={cn(status === "running" && "motion-safe:animate-spin")}
      />
      {t.admin.status[status]}
    </span>
  );
}
