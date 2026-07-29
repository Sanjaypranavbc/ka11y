"use client";

import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { useLanguage } from "@/components/dashboard/LanguageContext";

interface PageHeaderProps {
  title: string;
  target?: string;
  actions?: ReactNode;
}

export function PageHeader({ title, target, actions }: PageHeaderProps) {
  const { t } = useLanguage();

  return (
    <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-gray-10 px-4 py-4 sm:px-8 sm:py-0 sm:h-20 lg:px-16">
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <span className="text-[24px] font-medium leading-tight text-brand-teal sm:text-[32px] sm:leading-[42px]">
          {title}
        </span>
        {target && (
          <p className="flex items-center gap-1.5 text-[14px] leading-6 text-brand-green-80 sm:text-[16px]">
            <span>{t.common.target}</span>
            <a
              href={target}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-gray-40 hover:text-brand-green-80"
            >
              <span className="hidden sm:inline">{target}</span>
              <span className="sm:hidden">{t.common.link}</span>
              <ExternalLink size={13} aria-hidden="true" />
            </a>
          </p>
        )}
      </div>
      {actions && (
        <div className="flex items-center gap-2 sm:gap-6">{actions}</div>
      )}
    </header>
  );
}
