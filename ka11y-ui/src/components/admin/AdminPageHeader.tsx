"use client";

import type { ReactNode } from "react";
import { Calendar, CircleAlert, CircleCheck } from "lucide-react";
import { formatDateTime } from "@/lib/admin/format";
import { useNow } from "@/lib/admin/useNow";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

interface AdminPageHeaderProps {
  title: string;
  subtitle?: string;
  systemHealth?: "healthy" | "degraded";
  actions?: ReactNode;
}

export function AdminPageHeader({ title, subtitle, systemHealth, actions }: AdminPageHeaderProps) {
  const { t, lang } = useLanguage();
  const now = useNow(30_000);
  const healthy = systemHealth === "healthy";
  const HealthIcon = healthy ? CircleCheck : CircleAlert;

  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-[26px] font-semibold leading-8 text-gray-100 sm:text-[28px] sm:leading-9">{title}</h1>
        {subtitle && <p className="mt-1 text-[14px] leading-5 text-gray-80">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {now && (
          <p className="flex items-center gap-1.5 text-[14px] leading-5 text-gray-80">
            <Calendar size={16} aria-hidden="true" />
            <span className="sr-only">{t.admin.overview.currentTime}: </span>
            <time dateTime={new Date(now).toISOString()}>{formatDateTime(new Date(now).toISOString(), lang)}</time>
          </p>
        )}
        {systemHealth && (
          <p
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium leading-4",
              healthy ? "bg-adm-completed-bg text-adm-completed" : "bg-adm-review-bg text-adm-review",
            )}
          >
            <HealthIcon size={14} aria-hidden="true" />
            {healthy ? t.admin.overview.allOperational : t.admin.overview.degraded}
          </p>
        )}
        {actions}
      </div>
    </div>
  );
}
