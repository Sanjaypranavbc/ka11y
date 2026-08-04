"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { derivePageName, type WcagPageScan } from "@/lib/wcagAudit";
import type { Translations } from "@/lib/i18n/translations";
import { cn } from "@/lib/utils";

export function PageFilterDropdown({
  pages,
  selected,
  onChange,
  t,
}: {
  pages: WcagPageScan[];
  selected: string | null;
  onChange: (pageUrl: string | null) => void;
  t: Translations;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  if (pages.length === 0) return null;

  const selectedPage = pages.find((p) => p.page_url === selected);
  const label = selectedPage
    ? derivePageName(selectedPage.page_url, pages.indexOf(selectedPage))
    : t.filters.allPages;

  return (
    <div className="relative ml-auto" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-[16px] border border-gray-40 bg-gray-10 px-4 py-2 text-[14px] leading-6 text-gray-100 sm:text-[16px]"
      >
        {t.filters.page}: {label}
        <ChevronDown
          size={16}
          aria-hidden="true"
          className={cn("transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-10 mt-1 flex max-h-80 flex-col overflow-y-auto overflow-x-hidden rounded-[8px] border border-gray-40 bg-white shadow-md">
          <button
            type="button"
            onClick={() => { onChange(null); setOpen(false); }}
            className={cn(
              "whitespace-nowrap px-4 py-2 text-left text-[14px] leading-6 text-gray-100 hover:bg-gray-10 sm:text-[16px]",
              selected === null && "bg-brand-green-20 text-brand-teal-dark",
            )}
          >
            {t.filters.allPages}
          </button>
          {pages.map((page, index) => (
            <button
              key={page.page_url}
              type="button"
              onClick={() => { onChange(page.page_url); setOpen(false); }}
              className={cn(
                "flex items-center gap-2 whitespace-nowrap px-4 py-2 text-left text-[14px] leading-6 text-gray-100 hover:bg-gray-10 sm:text-[16px]",
                selected === page.page_url && "bg-brand-green-20 text-brand-teal-dark",
              )}
            >
              {derivePageName(page.page_url, index)}
              {page.status === "failed" && (
                <span className="rounded-[4px] bg-[#fde8e4] px-1.5 py-0.5 text-[11px] font-medium leading-4 text-[#c00000]">
                  {t.filters.pageFailed}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
