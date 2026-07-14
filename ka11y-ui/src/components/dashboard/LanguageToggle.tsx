"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

const LANGUAGES = ["EN", "JP"] as const;

export function LanguageToggle() {
  const [active, setActive] = useState<(typeof LANGUAGES)[number]>("EN");

  return (
    <div role="radiogroup" aria-label="Report language" className="inline-flex">
      {LANGUAGES.map((lang, i) => (
        <button
          key={lang}
          type="button"
          role="radio"
          aria-checked={active === lang}
          onClick={() => setActive(lang)}
          className={cn(
            "px-4 py-1 text-[14px] leading-5 transition-colors",
            i === 0 ? "rounded-l-[8px]" : "rounded-r-[8px]",
            active === lang
              ? "bg-brand-green-20 text-brand-teal-dark"
              : "bg-gray-10 text-gray-80",
          )}
        >
          {lang}
        </button>
      ))}
    </div>
  );
}
