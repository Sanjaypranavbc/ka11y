import type { Lang } from "@/lib/i18n/translations";

export const LOCALE: Record<Lang, string> = { en: "en-US", jp: "ja-JP" };

export function formatNumber(n: number, lang: Lang): string {
  return new Intl.NumberFormat(LOCALE[lang]).format(n);
}

/** 42774 -> "42.8K" (en) — used for stat cards and chart labels only; tables get the full number. */
export function formatCompact(n: number, lang: Lang): string {
  return new Intl.NumberFormat(LOCALE[lang], { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function formatPercent(part: number, total: number, lang: Lang): string {
  const ratio = total === 0 ? 0 : part / total;
  return new Intl.NumberFormat(LOCALE[lang], { style: "percent", maximumFractionDigits: 0 }).format(ratio);
}

export function formatTime(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(LOCALE[lang], { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));
}

export function formatDate(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(LOCALE[lang], { year: "numeric", month: "short", day: "numeric" }).format(new Date(iso));
}

export function formatDateTime(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(LOCALE[lang], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

export function formatBytes(bytes: number, lang: Lang): string {
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${new Intl.NumberFormat(LOCALE[lang], { maximumFractionDigits: 1 }).format(value)} ${units[i]}`;
}

/** Relative label; `Intl.RelativeTimeFormat` gives correct EN/JA wording for free. */
export function formatRelative(iso: string, now: number, lang: Lang): string {
  const diff = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  const rtf = new Intl.RelativeTimeFormat(LOCALE[lang], { numeric: "always", style: "narrow" });
  if (diff < 60) return rtf.format(-diff, "second");
  if (diff < 3600) return rtf.format(-Math.round(diff / 60), "minute");
  if (diff < 86_400) return rtf.format(-Math.round(diff / 3600), "hour");
  return rtf.format(-Math.round(diff / 86_400), "day");
}
