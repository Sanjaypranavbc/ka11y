"use client";

import { useState } from "react";
import { ImageOff } from "lucide-react";
import { cn } from "@/lib/utils";

/** Renders the captured element image for a finding row. `srcs` is an ordered
 * list of candidate URLs (captured crop first, original image, then lazy-load
 * / background-image sources); the first that loads is shown. When the list is
 * empty or every candidate fails, shows an explicit "no preview" state instead
 * of a blank box that reads as a broken image. */
export function ElementImage({
  srcs,
  className,
  alt = "Captured element",
}: {
  srcs: string[] | null | undefined;
  className?: string;
  alt?: string;
}) {
  const [idx, setIdx] = useState(0);
  const box = cn(
    "overflow-hidden rounded-[8px] shadow-[0px_0px_18px_0px_rgba(0,0,0,0.09)]",
    className,
  );

  const list = (srcs ?? []).filter(Boolean);
  const current = idx < list.length ? list[idx] : null;

  // No image available for this finding (e.g. non-image rule, or the crawler
  // captured no source). Show an explicit, intentional empty state.
  if (!current) {
    return (
      <div
        className={cn(
          box,
          "flex flex-col items-center justify-center gap-1 border border-dashed border-gray-40 bg-gray-10 text-gray-60",
        )}
        role="img"
        aria-label="No image preview available"
      >
        <ImageOff className="h-4 w-4" aria-hidden="true" />
        <span className="text-[10px] leading-none">No preview</span>
      </div>
    );
  }

  return (
    <div className={cn(box, "bg-gray-10")}>
      <img
        src={current}
        alt={alt}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setIdx((i) => i + 1)}
        className="h-full w-full object-contain"
      />
    </div>
  );
}
