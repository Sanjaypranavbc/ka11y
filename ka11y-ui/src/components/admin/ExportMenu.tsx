"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { ChevronDown, FileDown } from "lucide-react";
import { exportAuditHref } from "@/lib/admin/api";
import { EXPORT_FORMATS, type ExportFormat } from "@/lib/admin/data";
import { useDismissable } from "@/lib/admin/useFocusTrap";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

export interface ExportMenuLabels {
  button: string;
  buttonFor: (subject: string) => string;
  menuLabel: (subject: string) => string;
  formats: Record<ExportFormat, string>;
}

interface ExportMenuProps {
  jobId: string;
  /** Read to screen readers so every row's button is distinguishable. */
  subject: string;
  /** Formats to list; defaults to the admin console's set. */
  formats?: readonly ExportFormat[];
  /** Builds each item's download URL; defaults to the admin export endpoint. */
  hrefFor?: (jobId: string, format: ExportFormat) => string;
  /** Labels; default to the admin console's translations. */
  labels?: ExportMenuLabels;
  /** Renders the button inert (no job to export yet). */
  disabled?: boolean;
  className?: string;
}

const MENU_WIDTH = 208;

/**
 * "Export" menu button (WAI-ARIA menu-button pattern) with one download
 * link per format. The menu is position: fixed so the table's horizontal
 * scroll region cannot clip it; it closes on scroll, resize, Escape, Tab and
 * outside clicks, and returns focus to the button.
 */
export function ExportMenu({
  jobId,
  subject,
  formats = EXPORT_FORMATS,
  hrefFor = exportAuditHref,
  labels: labelsProp,
  disabled = false,
  className,
}: ExportMenuProps) {
  const { t } = useLanguage();
  const labels = labelsProp ?? t.admin.pages.reports.export;
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  const menuId = useId();
  useDismissable(open, () => setOpen(false), wrapperRef, buttonRef);

  useEffect(() => {
    if (!open) return;
    const place = () => {
      const r = buttonRef.current?.getBoundingClientRect();
      if (!r) return;
      const left = Math.max(8, Math.min(r.right - MENU_WIDTH, window.innerWidth - MENU_WIDTH - 8));
      setPos({ top: r.bottom + 4, left });
    };
    place();
    const close = () => setOpen(false);
    window.addEventListener("resize", close);
    // Capture phase: the table's scroll region does not bubble scroll events to window.
    document.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("resize", close);
      document.removeEventListener("scroll", close, true);
    };
  }, [open]);

  // The menu only exists once `pos` is known, so focus moves in after that render.
  useEffect(() => {
    if (open && pos) itemRefs.current[0]?.focus();
  }, [open, pos]);

  function close() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const items = itemRefs.current.filter(Boolean) as HTMLElement[];
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      items[(index + 1) % items.length]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length]?.focus();
    } else if (event.key === "Home") {
      event.preventDefault();
      items[0]?.focus();
    } else if (event.key === "End") {
      event.preventDefault();
      items[items.length - 1]?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div ref={wrapperRef} className="relative inline-block">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        // Hover darkens the text too: green-80 on the pale green fill is only 4.3:1.
        className={cn(
          "inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-brand-green-80 px-3 text-[14px] font-medium text-brand-green-80 hover:bg-adm-completed-bg hover:text-brand-teal-dark disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-brand-green-80",
          className,
        )}
      >
        <FileDown size={16} aria-hidden="true" />
        <span>
          {labels.button}
          <span className="sr-only"> {labels.buttonFor(subject)}</span>
        </span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && pos && (
        <div
          id={menuId}
          role="menu"
          aria-label={labels.menuLabel(subject)}
          onKeyDown={onMenuKeyDown}
          style={{ position: "fixed", top: pos.top, left: pos.left, width: MENU_WIDTH }}
          className="z-40 rounded-xl border border-adm-border bg-white p-1.5 shadow-[0_8px_24px_rgba(0,0,0,0.12)]"
        >
          {formats.map((format: ExportFormat, i) => (
            <a
              key={format}
              ref={(el) => {
                itemRefs.current[i] = el;
              }}
              role="menuitem"
              tabIndex={-1}
              href={hrefFor(jobId, format)}
              download
              onClick={close}
              className={cn(
                "flex min-h-11 w-full items-center gap-2 whitespace-nowrap rounded-lg px-3 text-left text-[14px] leading-5 text-gray-100 hover:bg-gray-10",
              )}
            >
              {/* Decorative badge: the label already names the format. */}
              <span aria-hidden="true" className="inline-block w-10 text-[12px] font-semibold uppercase tracking-wide text-gray-80">
                {format}
              </span>
              {labels.formats[format]}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
