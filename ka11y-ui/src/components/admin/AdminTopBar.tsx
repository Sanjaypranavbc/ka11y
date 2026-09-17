"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { Bell, ChevronDown, LogOut, Menu, Search, UserRound } from "lucide-react";
import type { AdminNotification, AdminUser } from "@/lib/admin/data";
import { formatRelative } from "@/lib/admin/format";
import { useDismissable } from "@/lib/admin/useFocusTrap";
import { useNow } from "@/lib/admin/useNow";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { AdminBrand } from "@/components/admin/AdminBrand";
import { LANGUAGES, type Lang } from "@/lib/i18n/translations";
import { LOGOUT_URL } from "@/lib/auth";
import { cn } from "@/lib/utils";

const LANG_LABEL: Record<Lang, string> = { en: "English", jp: "日本語" };

interface AdminTopBarProps {
  user: AdminUser | null;
  notifications: AdminNotification[];
  onOpenMobileNav: () => void;
}

export function AdminTopBar({ user, notifications, onOpenMobileNav }: AdminTopBarProps) {
  const { t } = useLanguage();
  const searchId = useId();

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-2 border-b border-adm-border bg-white px-3 sm:gap-4 sm:px-6">
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label={t.admin.topBar.openMenu}
        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-100 hover:bg-gray-10 md:hidden"
      >
        <Menu size={22} aria-hidden="true" />
      </button>
      {/* Hidden on the narrowest screens so the search field keeps a usable width; the brand is in the nav dialog. */}
      <AdminBrand className="hidden sm:flex md:hidden" wordmark={false} />

      <form
        role="search"
        className="relative min-w-0 flex-1"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <label htmlFor={searchId} className="sr-only">
          {t.admin.topBar.searchLabel}
        </label>
        <input
          id={searchId}
          type="search"
          name="q"
          placeholder={t.admin.topBar.searchPlaceholder}
          autoComplete="off"
          className="h-11 w-full min-w-0 rounded-xl border border-adm-border bg-gray-10 pl-11 pr-3 text-[15px] leading-5 text-gray-100 placeholder:text-gray-80 focus:bg-white"
        />
        {/* The magnifier is the real submit control (44px target), not decoration. */}
        <button
          type="submit"
          aria-label={t.admin.topBar.searchSubmit}
          className="absolute left-0 top-0 inline-flex h-11 w-11 items-center justify-center rounded-l-xl text-gray-80 hover:text-gray-100"
        >
          <Search size={18} aria-hidden="true" />
        </button>
      </form>

      <NotificationsPopover notifications={notifications} />
      <AccountMenu user={user} />
    </header>
  );
}

function NotificationsPopover({ notifications: initial }: { notifications: AdminNotification[] }) {
  const { t, lang } = useLanguage();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(initial);
  // Adopt a new list from the shell's refresh while keeping local read marks otherwise.
  const [lastInitial, setLastInitial] = useState(initial);
  if (initial !== lastInitial) {
    setLastInitial(initial);
    setItems(initial);
  }
  const wrapperRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const panelId = useId();
  const now = useNow(30_000);
  useDismissable(open, () => setOpen(false), wrapperRef, buttonRef);

  useEffect(() => {
    if (open) headingRef.current?.focus();
  }, [open]);

  const unread = items.filter((n) => !n.read).length;

  return (
    <div ref={wrapperRef} className="relative shrink-0">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={unread > 0 ? t.admin.topBar.notificationsUnread(unread) : t.admin.topBar.notifications}
        onClick={() => setOpen((v) => !v)}
        className="relative inline-flex h-11 w-11 items-center justify-center rounded-lg text-gray-100 hover:bg-gray-10"
      >
        <Bell size={20} aria-hidden="true" />
        {unread > 0 && (
          <span aria-hidden="true" className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full border-2 border-white bg-adm-failed" />
        )}
      </button>
      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-labelledby={`${panelId}-heading`}
          className="absolute right-0 top-full z-40 mt-2 w-[min(calc(100vw-24px),360px)] rounded-xl border border-adm-border bg-white p-2 shadow-[0_8px_24px_rgba(0,0,0,0.12)]"
        >
          <div className="flex items-center justify-between px-2 py-1.5">
            <h2 id={`${panelId}-heading`} ref={headingRef} tabIndex={-1} className="text-[15px] font-semibold leading-5 text-gray-100">
              {t.admin.topBar.notificationsHeading}
            </h2>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => setItems((list) => list.map((n) => ({ ...n, read: true })))}
                className="min-h-11 rounded-md px-2 text-[13px] font-medium text-brand-green-80 hover:underline"
              >
                {t.admin.topBar.markAllRead}
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="px-2 py-3 text-[14px] leading-5 text-gray-80">{t.admin.topBar.noNotifications}</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto">
              {items.map((n) => (
                <li key={n.id} className="flex items-start gap-2 rounded-lg px-2 py-2.5 hover:bg-gray-10">
                  <span
                    aria-hidden="true"
                    className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", n.read ? "bg-gray-40" : "bg-adm-running")}
                  />
                  <div className="min-w-0">
                    <p className={cn("text-[14px] leading-5 text-gray-100", !n.read && "font-medium")}>
                      {!n.read && <span className="sr-only">{t.admin.topBar.unread}: </span>}
                      {n.title}
                    </p>
                    <p className="text-[12px] leading-4 text-gray-80">{now ? formatRelative(n.at, now, lang) : ""}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function AccountMenu({ user }: { user: AdminUser | null }) {
  const { t, lang, setLang } = useLanguage();
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLElement | null)[]>([]);
  const menuId = useId();
  useDismissable(open, () => setOpen(false), wrapperRef, buttonRef);

  useEffect(() => {
    if (open) itemRefs.current[0]?.focus();
  }, [open]);

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

  const initial = user?.name?.charAt(0).toUpperCase() ?? "?";
  // Menu order: profile (0), one radio per language (1..n), sign out (n+1).
  const signOutIndex = 1 + LANGUAGES.length;
  const itemClass =
    "flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-[14px] leading-5 text-gray-100 hover:bg-gray-10";

  return (
    <div ref={wrapperRef} className="relative shrink-0">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-11 items-center gap-2 rounded-lg px-1.5 hover:bg-gray-10 sm:px-2"
      >
        <span
          aria-hidden="true"
          className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-gray-10 text-[14px] font-semibold text-gray-100"
        >
          {initial}
        </span>
        <span className="hidden text-left sm:block">
          <span className="block text-[14px] font-medium leading-4 text-gray-100">{user?.name ?? "—"}</span>
          <span className="block text-[12px] leading-4 text-gray-80">{user?.role ?? ""}</span>
        </span>
        <span className="sr-only">{t.admin.topBar.accountMenu}</span>
        <ChevronDown size={16} aria-hidden="true" className="text-gray-80" />
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label={t.admin.topBar.accountMenu}
          onKeyDown={onMenuKeyDown}
          className="absolute right-0 top-full z-40 mt-2 w-56 rounded-xl border border-adm-border bg-white p-1.5 shadow-[0_8px_24px_rgba(0,0,0,0.12)]"
        >
          {user && (
            <p className="px-3 py-2 text-[12px] leading-4 text-gray-80">{user.email}</p>
          )}
          <Link
            ref={(el) => {
              itemRefs.current[0] = el;
            }}
            href="/admin/settings" role="menuitem" tabIndex={-1} onClick={close} className={itemClass}>
            <UserRound size={16} aria-hidden="true" />
            {t.admin.topBar.profile}
          </Link>
          <div role="group" aria-label={t.admin.topBar.languageLabel} className="my-1 border-y border-adm-border py-1">
            <p className="px-3 py-1 text-[12px] font-medium uppercase leading-4 tracking-wide text-gray-80">
              {t.admin.topBar.languageLabel}
            </p>
            {LANGUAGES.map((l, i) => (
              <button
                key={l}
                ref={(el) => {
                  itemRefs.current[1 + i] = el;
                }}
                type="button"
                role="menuitemradio"
                aria-checked={lang === l}
                tabIndex={-1}
                lang={l === "jp" ? "ja" : "en"}
                onClick={() => {
                  setLang(l);
                  close();
                }}
                className={cn(itemClass, lang === l && "font-medium text-brand-teal-dark")}
              >
                <span aria-hidden="true" className="inline-block w-4 text-center">
                  {lang === l ? "●" : ""}
                </span>
                {LANG_LABEL[l]}
              </button>
            ))}
          </div>
          {/* Plain anchor: this is a rewrite to the Python API that ends the session. */}
          <a
            ref={(el) => {
              itemRefs.current[signOutIndex] = el;
            }}
            href={LOGOUT_URL} role="menuitem" tabIndex={-1} className={itemClass}>
            <LogOut size={16} aria-hidden="true" />
            {t.admin.topBar.signOut}
          </a>
        </div>
      )}
    </div>
  );
}
