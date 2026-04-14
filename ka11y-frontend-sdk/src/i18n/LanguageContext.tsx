import { createContext, useCallback, useContext, useState } from "react";
import { Lang, TranslationKey, translations } from "./translations";

// ── Types ─────────────────────────────────────────────────────────────────────

interface LanguageContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  /** Translate a key, optionally interpolating {placeholder} tokens. */
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
}

// ── Context ───────────────────────────────────────────────────────────────────

const LanguageContext = createContext<LanguageContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

const LANGUAGE_STORAGE_KEY = "ka11y_ui_lang";

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY) as Lang;
    return saved === "en" || saved === "ja" ? saved : "en";
  });

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, next);
  }, []);

  const t = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>): string => {
      // Look up in current language, fall back to English
      const dict = translations[lang] as Record<string, string>;
      const fallback = translations.en as Record<string, string>;
      let str = dict[key] ?? fallback[key] ?? key;

      // Interpolate {placeholder} tokens
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          str = str.replaceAll(`{${k}}`, String(v));
        }
      }
      return str;
    },
    [lang],
  );

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used inside <LanguageProvider>");
  return ctx;
}
