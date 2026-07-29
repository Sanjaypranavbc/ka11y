"use client";

import { LANGUAGES, type Lang } from "@/lib/i18n/translations";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

const LABELS: Record<Lang, string> = { en: "EN", jp: "JP" };

export function LanguageToggle() {
  const { lang, setLang } = useLanguage();

  return (
    <div role="radiogroup" aria-label="Report language" className="inline-flex">
      {LANGUAGES.map((l, i) => (
        <button
          key={l}
          type="button"
          role="radio"
          aria-checked={lang === l}
          onClick={() => setLang(l)}
          className={cn(
            "px-4 py-1 text-[14px] leading-5 transition-colors",
            i === 0 ? "rounded-l-[8px]" : "rounded-r-[8px]",
            lang === l
              ? "bg-brand-green-20 text-brand-teal-dark"
              : "bg-gray-10 text-gray-80",
          )}
        >
          {LABELS[l]}
        </button>
      ))}
    </div>
  );
}
