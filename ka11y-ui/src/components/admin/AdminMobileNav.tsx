"use client";

import { useRef } from "react";
import { X } from "lucide-react";
import { AdminBrand } from "@/components/admin/AdminBrand";
import { AdminNavList } from "@/components/admin/AdminNavList";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { useFocusTrap } from "@/lib/admin/useFocusTrap";

interface AdminMobileNavProps {
  open: boolean;
  onClose: () => void;
}

/** Off-canvas navigation for < md widths, presented as a modal dialog. */
export function AdminMobileNav({ open, onClose }: AdminMobileNavProps) {
  const { t } = useLanguage();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useFocusTrap(panelRef, open, { onEscape: onClose, initialFocus: closeRef });

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden">
      <div aria-hidden="true" onClick={onClose} className="absolute inset-0 bg-gray-100/40" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={t.admin.navLabel}
        tabIndex={-1}
        className="admin-drawer-enter absolute inset-y-0 left-0 flex w-[min(100%,320px)] flex-col bg-white shadow-xl"
      >
        <div className="flex h-16 items-center justify-between border-b border-adm-border px-4">
          <AdminBrand />
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label={t.admin.topBar.closeMenu}
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-gray-80 hover:bg-gray-10"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>
        <nav aria-label={t.admin.navLabel} className="flex-1 overflow-y-auto px-3 py-5">
          <AdminNavList onNavigate={onClose} idPrefix="mobile" />
        </nav>
        <p className="border-t border-adm-border px-5 py-4 text-[13px] leading-5 text-gray-80">{t.admin.tagline}</p>
      </div>
    </div>
  );
}
