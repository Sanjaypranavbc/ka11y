import { useEffect, useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronRight, Search, AlertCircle, Loader2 } from "lucide-react";
import { useLanguage } from "@/i18n/LanguageContext";

// ── Types ─────────────────────────────────────────────────────────────────────

interface WcagRule {
  id: string;
  level: "A" | "AA" | "AAA";
  severity: "critical" | "high" | "medium" | "low" | null;
  name: string;
  description: string;
  suggested_fix: string;
}

interface WcagRulesResponse {
  version: string;
  lang: string;
  rules: WcagRule[];
}

type LevelFilter = "all" | "A" | "AA" | "AAA";

// ── Severity helpers ──────────────────────────────────────────────────────────

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800",
  high:     "bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-800",
  medium:   "bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800",
  low:      "bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800",
};

const LEVEL_STYLES: Record<string, string> = {
  A:   "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800",
  AA:  "bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800",
  AAA: "bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-900/30 dark:text-purple-400 dark:border-purple-800",
};

// ── Row component ─────────────────────────────────────────────────────────────

function RuleRow({ rule }: { rule: WcagRule }) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-border rounded-md overflow-hidden">
      <button
        className="w-full text-left flex items-start gap-3 px-4 py-3 hover:bg-muted/40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls={`rule-body-${rule.id}`}
      >
        {/* Chevron */}
        <span className="mt-0.5 shrink-0 text-muted-foreground">
          {expanded
            ? <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            : <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          }
        </span>

        {/* SC ID */}
        <span className="font-mono text-xs font-semibold text-foreground w-12 shrink-0 pt-px">
          {rule.id}
        </span>

        {/* Level badge */}
        <span className={cn(
          "text-[9px] font-bold px-1.5 py-0.5 rounded border tracking-wider shrink-0 mt-px",
          LEVEL_STYLES[rule.level] ?? "",
        )}>
          {rule.level}
        </span>

        {/* Name + description */}
        <span className="flex-1 min-w-0">
          <span className="text-xs font-semibold text-foreground">{rule.name}</span>
          <span className="block text-[10px] text-muted-foreground mt-0.5 leading-relaxed line-clamp-2">
            {rule.description}
          </span>
        </span>

        {/* Severity badge (optional) */}
        {rule.severity && (
          <span className={cn(
            "text-[9px] font-bold px-1.5 py-0.5 rounded border tracking-wider shrink-0 mt-px capitalize",
            SEVERITY_STYLES[rule.severity] ?? "",
          )}>
            {rule.severity}
          </span>
        )}
      </button>

      {/* Expanded body */}
      {expanded && (
        <div
          id={`rule-body-${rule.id}`}
          className="border-t border-border bg-muted/20 px-4 py-4 space-y-3"
        >
          <div>
            <p className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground mb-1">
              {t("wcagRules.description")}
            </p>
            <p className="text-xs text-foreground leading-relaxed">{rule.description}</p>
          </div>
          {rule.suggested_fix && (
            <div>
              <p className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground mb-1">
                {t("wcagRules.suggestedFix")}
              </p>
              <p className="text-xs text-foreground leading-relaxed font-mono bg-card border border-border rounded px-3 py-2 whitespace-pre-wrap">
                {rule.suggested_fix}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function WcagRulesTab() {
  const { t, lang } = useLanguage();
  const [rules, setRules]     = useState<WcagRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [search, setSearch]   = useState("");
  const [level, setLevel]     = useState<LevelFilter>("all");

  // Fetch rules when lang changes
  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/v1/rules/wcag?lang=${encodeURIComponent(lang)}`, {
      headers: { Accept: "application/json" },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`Server returned ${r.status}`);
        return r.json() as Promise<WcagRulesResponse>;
      })
      .then((data) => {
        setRules(data.rules ?? []);
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to load rules");
        setLoading(false);
      });
  }, [lang]);

  // Filter + search (client-side, instant)
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rules.filter((r) => {
      const matchLevel  = level === "all" || r.level === level;
      const matchSearch = !q
        || r.id.toLowerCase().includes(q)
        || r.name.toLowerCase().includes(q)
        || r.description.toLowerCase().includes(q);
      return matchLevel && matchSearch;
    });
  }, [rules, search, level]);

  // Level counts
  const counts = useMemo(
    () => ({
      all: rules.length,
      A:   rules.filter((r) => r.level === "A").length,
      AA:  rules.filter((r) => r.level === "AA").length,
      AAA: rules.filter((r) => r.level === "AAA").length,
    }),
    [rules],
  );

  return (
    <div className="p-3 sm:p-5 space-y-4 max-w-4xl">

      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground">{t("wcagRules.title")}</h2>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            {loading ? t("wcagRules.loading") : t("wcagRules.count", { n: filtered.length, total: rules.length })}
          </p>
        </div>
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap gap-2 items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-48">
          <Search
            className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none"
            aria-hidden="true"
          />
          <Input
            placeholder={t("wcagRules.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-8 text-xs bg-input border-border focus-visible:ring-primary/50"
            aria-label={t("wcagRules.searchPlaceholder")}
          />
        </div>

        {/* Level filter */}
        <div className="flex rounded-md overflow-hidden border border-border text-[10px] font-semibold" role="group" aria-label="Filter by WCAG level">
          {(["all", "A", "AA", "AAA"] as LevelFilter[]).map((lvl) => (
            <button
              key={lvl}
              type="button"
              onClick={() => setLevel(lvl)}
              className={cn(
                "px-2.5 py-1.5 transition-colors cursor-pointer",
                level === lvl
                  ? "bg-primary text-primary-foreground"
                  : "bg-input text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={level === lvl}
            >
              {lvl === "all" ? t("wcagRules.all") : lvl}
              <span className="ml-1 opacity-60">
                {counts[lvl]}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Body */}
      {loading ? (
        <div className="flex items-center gap-2 py-12 justify-center text-muted-foreground text-xs">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t("wcagRules.loading")}
        </div>
      ) : error ? (
        <div
          role="alert"
          className="flex items-center gap-2 px-4 py-3 rounded border border-destructive/30 bg-destructive/5 text-destructive text-xs"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {error}
        </div>
      ) : filtered.length === 0 ? (
        <p className="text-xs text-muted-foreground py-12 text-center">
          {t("wcagRules.noMatch")}
        </p>
      ) : (
        <div className="space-y-1.5">
          {filtered.map((rule) => (
            <RuleRow key={rule.id} rule={rule} />
          ))}
        </div>
      )}
    </div>
  );
}
