"use client";

import { useState } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * A small info icon that shows a floating tooltip on hover/focus.
 * Renders inline next to a field label (e.g. "Crawl Depth").
 *
 * The tooltip is positioned absolutely so it always floats above the
 * form card regardless of the label's natural flow — matching the
 * reference screenshot where the popover sits centered over the card.
 */
export function InfoTooltip({
  title,
  description,
  levels,
  className,
}: {
  title: string;
  description: string;
  levels: { label: string; body: string }[];
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <span
      className={cn("relative inline-flex align-middle", className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      tabIndex={0}
      role="button"
      aria-label={title}
      aria-expanded={open}
    >
      <span
        className={cn(
          "flex h-4 w-4 items-center justify-center rounded-full",
          "border border-brand-teal text-brand-teal transition-colors",
          open ? "bg-brand-teal text-white" : "bg-transparent",
        )}
        aria-hidden="true"
      >
        <Info width={11} height={11} strokeWidth={2.2} />
      </span>

      {open && (
        <div
          role="tooltip"
          className={cn(
            "absolute z-50 top-full left-1/2 -translate-x-1/2 mt-2",
            "w-[280px] rounded-[12px] border border-gray-20 bg-white",
            "px-4 py-3 shadow-lg",
            "animate-in fade-in zoom-in-95 duration-150",
          )}
        >
          <div className="flex flex-col gap-2">
            {levels.map((lvl, i) => (
              <div key={lvl.label} className={cn("flex flex-col gap-0.5", i > 0 && "border-t border-gray-10 pt-2")}>
                <span className="text-[13px] font-medium leading-5 text-gray-100">
                  {lvl.label}
                </span>
                <span className="text-[12px] leading-5 text-gray-60">
                  {lvl.body}
                </span>
              </div>
            ))}
            <span className="text-[11px] leading-4 text-gray-40">
              {description}
            </span>
          </div>
          {/* Triangle pointer */}
          <span
            className="absolute -top-1 left-1/2 -translate-x-1/2"
            aria-hidden="true"
          >
            <svg width="12" height="6" viewBox="0 0 12 6" fill="none">
              <path d="M6 0L12 6H0L6 0Z" fill="white" />
            </svg>
            <svg
              width="12"
              height="6"
              viewBox="0 0 12 6"
              fill="none"
              className="absolute top-0 left-1/2 -translate-x-1/2"
            >
              <path d="M6 0L12 6H0L6 0Z" stroke="#E5E5E0" strokeWidth="0.5" />
            </svg>
          </span>
        </div>
      )}
    </span>
  );
}