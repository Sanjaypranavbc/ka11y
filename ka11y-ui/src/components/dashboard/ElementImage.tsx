"use client";

import { useState } from "react";
import { ImageOff } from "lucide-react";
import { cn } from "@/lib/utils";

/** Renders the captured element image for a finding row. `srcs` is an ordered
 * list of candidate URLs (captured crop first, original image, then lazy-load
 * / background-image sources); the first that loads is shown. When the list is
 * empty or every candidate fails, shows an explicit "no preview" state instead
 * of a blank box that reads as a broken image. While the current candidate is
 * still loading, an indeterminate progress bar (brand teal) fills the box —
 * `<img>` gives no real byte-progress, so this signals "still working" rather
 * than trying to fake a percentage. */
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
  const [loaded, setLoaded] = useState(false);
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
    <div className={cn(box, "relative bg-gray-10")}>
      {!loaded && (
        <div className="absolute inset-x-0 top-0 z-10 h-1 overflow-hidden bg-gray-40">
          <div className="h-full w-1/3 animate-[element-image-loading_1.1s_ease-in-out_infinite] rounded-full bg-brand-teal-dark" />
        </div>
      )}
      <img
        key={current}
        src={current}
        alt={alt}
        loading="lazy"
        referrerPolicy="no-referrer"
        onLoad={() => setLoaded(true)}
        onError={() => {
          setLoaded(false);
          setIdx((i) => i + 1);
        }}
        className={cn("h-full w-full object-contain transition-opacity", loaded ? "opacity-100" : "opacity-0")}
      />
    </div>
  );
}
