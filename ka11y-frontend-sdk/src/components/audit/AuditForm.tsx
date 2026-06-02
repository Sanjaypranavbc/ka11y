import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { AuditConfig } from "@/types/audit";
import {
  Play,
  Loader2,
  ChevronDown,
  CheckCircle,
  XCircle,
  SlidersHorizontal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/i18n/LanguageContext";
import { TranslationKey } from "@/i18n/translations";

// The 20 optional audit-module toggles. Collapsed under "Advanced checks".
const TOGGLE_ITEMS: { key: keyof AuditConfig; labelKey: TranslationKey }[] = [
  { key: "run_ocr",                          labelKey: "toggle.ocr"             },
  { key: "run_image_audit",                  labelKey: "toggle.imageAudit"      },
  { key: "run_form_audit",                   labelKey: "toggle.formAudit"       },
  { key: "run_label_in_name_audit",          labelKey: "toggle.labelInName"     },
  { key: "run_media_audit",                  labelKey: "toggle.mediaAudit"      },
  { key: "run_captions_audit",               labelKey: "toggle.captionsAudit"   },
  { key: "run_sensory_audit",                labelKey: "toggle.sensoryAudit"    },
  { key: "run_pause_stop_hide_audit",        labelKey: "toggle.pauseStop"       },
  { key: "run_target_size_audit",            labelKey: "toggle.targetSize"      },
  { key: "run_resize_text_audit",            labelKey: "toggle.resizeText"      },
  { key: "run_reflow_audit",                 labelKey: "toggle.reflow"          },
  { key: "run_text_spacing_audit",           labelKey: "toggle.textSpacing"     },
  { key: "run_orientation_audit",            labelKey: "toggle.orientation"     },
  { key: "run_hover_focus_content_audit",    labelKey: "toggle.hoverFocus"      },
  { key: "run_focus_not_obscured_min_audit", labelKey: "toggle.focusObscured"   },
  { key: "run_focus_not_obscured_enh_audit", labelKey: "toggle.focusObscuredPlus" },
  { key: "run_node_audit",                   labelKey: "toggle.runNodeAudit"    },
  { key: "run_consistent_navigation_audit",  labelKey: "toggle.consistentNav"   },
  { key: "run_consistent_id_audit",          labelKey: "toggle.consistentId"    },
  { key: "run_unusual_words_audit",          labelKey: "toggle.unusualWords"    },
  { key: "run_section_headings_audit",       labelKey: "toggle.sectionHeadings" },
];

const STATUS_KEYS: Record<string, TranslationKey> = {
  pending:   "status.pending",
  running:   "status.running",
  completed: "status.completed",
  failed:    "status.failed",
};

interface AuditFormProps {
  config: AuditConfig;
  onConfigChange: (config: AuditConfig) => void;
  onRunAudit: (config: AuditConfig) => void;
  jobStatus: "idle" | "pending" | "running" | "completed" | "failed";
  currentStage?: string;
  /** Called right after a run is kicked off (e.g. to close a drawer). */
  onSubmitted?: () => void;
}

export function AuditForm({
  config,
  onConfigChange,
  onRunAudit,
  jobStatus,
  currentStage,
  onSubmitted,
}: AuditFormProps) {
  const { t } = useLanguage();
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const isRunning = jobStatus === "pending" || jobStatus === "running";
  const update = (patch: Partial<AuditConfig>) => onConfigChange({ ...config, ...patch });
  const enabledCount = TOGGLE_ITEMS.filter((it) => config[it.key] as boolean).length;

  const setAllChecks = (value: boolean) => {
    const patch = {} as Partial<AuditConfig>;
    for (const it of TOGGLE_ITEMS) (patch as Record<string, boolean>)[it.key] = value;
    update(patch);
  };

  const handleRun = () => {
    localStorage.setItem("ka11y_last_url", config.url);
    localStorage.setItem("ka11y_last_lang", config.lang);
    onRunAudit(config);
    onSubmitted?.();
  };

  return (
    <div className="space-y-4">
      {/* URL */}
      <div className="space-y-1.5">
        <Label htmlFor="audit-url" className="text-[10px] tracking-widest uppercase text-muted-foreground font-semibold">
          {t("sidebar.targetUrl")}
        </Label>
        <Input
          id="audit-url"
          value={config.url}
          onChange={(e) => update({ url: e.target.value })}
          onKeyDown={(e) => { if (e.key === "Enter" && config.url && !isRunning) handleRun(); }}
          placeholder={t("sidebar.urlPlaceholder")}
          className="h-10 text-sm font-mono bg-[hsl(var(--input))] border-border focus-visible:ring-primary/50"
        />
      </div>

      {/* Depth / pages / level */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="audit-max-depth" className="text-[10px] tracking-widest uppercase text-muted-foreground font-semibold">
            {t("sidebar.maxDepth")}
          </Label>
          <Input
            id="audit-max-depth"
            type="number"
            min={0}
            max={5}
            value={config.max_depth}
            onChange={(e) => {
              const n = Math.max(0, Math.min(5, Math.floor(Number(e.target.value) || 0)));
              update({ max_depth: n });
            }}
            className="mt-1.5 h-9 text-sm font-mono bg-[hsl(var(--input))] border-border focus-visible:ring-primary/50"
          />
        </div>
        <div>
          <Label htmlFor="audit-max-pages" className="text-[10px] tracking-widest uppercase text-muted-foreground font-semibold">
            {t("sidebar.maxPages")}
          </Label>
          <Input
            id="audit-max-pages"
            type="number"
            min={1}
            max={200}
            value={config.max_pages}
            disabled={config.max_depth === 0}
            onChange={(e) => {
              const n = Math.max(1, Math.min(200, Math.floor(Number(e.target.value) || 1)));
              update({ max_pages: n });
            }}
            className="mt-1.5 h-9 text-sm font-mono bg-[hsl(var(--input))] border-border focus-visible:ring-primary/50 disabled:opacity-60 disabled:cursor-not-allowed"
          />
        </div>
      </div>

      <p
        className={cn(
          "text-[11px] leading-tight rounded px-2 py-1.5",
          config.max_depth === 0 ? "text-muted-foreground bg-muted/40" : "text-primary bg-primary/10 font-medium"
        )}
      >
        {config.max_depth === 0
          ? t("sidebar.depthHintSingle")
          : t("sidebar.depthHintMulti", { pages: config.max_pages, depth: config.max_depth })}
      </p>

      <div className="flex items-center justify-between">
        <Label htmlFor="audit-internal-links" className="text-xs font-medium text-muted-foreground cursor-pointer">
          {t("sidebar.internalLinks")}
        </Label>
        <Switch
          id="audit-internal-links"
          checked={config.internal_links}
          onCheckedChange={(v) => update({ internal_links: v })}
          className="data-[state=checked]:bg-primary"
        />
      </div>

      <div>
        <Label className="text-[10px] tracking-widest uppercase text-muted-foreground font-semibold">
          {t("sidebar.wcagLevel")}
        </Label>
        <div className="mt-1.5 flex rounded-md overflow-hidden border border-border text-xs font-semibold">
          {(["A", "AA", "AAA"] as const).map((lvl) => (
            <button
              key={lvl}
              type="button"
              onClick={() => update({ wcag_level: lvl })}
              aria-pressed={config.wcag_level === lvl}
              className={cn(
                "flex-1 cursor-pointer py-2 transition-colors",
                config.wcag_level === lvl
                  ? "bg-primary text-primary-foreground"
                  : "bg-[hsl(var(--input))] text-muted-foreground hover:text-foreground"
              )}
            >
              {lvl}
            </button>
          ))}
        </div>
      </div>

      {/* Engine Selection — axe-core and AccessLint toggles */}
      <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-2.5">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-primary animate-pulse shrink-0" aria-hidden="true" />
          <span className="text-xs font-semibold text-foreground">{t("engines.title" as TranslationKey)}</span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-snug">
          {t("engines.hint" as TranslationKey)}
        </p>
        <div className="grid grid-cols-2 gap-2">
          {/* axe-core Engine Card */}
          <button
            type="button"
            onClick={() => update({ run_axe: !config.run_axe })}
            className={cn(
              "relative flex flex-col items-start gap-1 rounded-lg border px-3 py-2.5 text-left transition-all cursor-pointer",
              config.run_axe
                ? "border-blue-500/50 bg-blue-500/10 shadow-sm shadow-blue-500/10"
                : "border-border bg-card opacity-60 hover:opacity-80"
            )}
          >
            <div className="flex items-center gap-1.5 w-full">
              <div className={cn(
                "h-1.5 w-1.5 rounded-full shrink-0",
                config.run_axe ? "bg-blue-500" : "bg-muted-foreground/30"
              )} />
              <span className={cn(
                "text-xs font-bold uppercase tracking-wider",
                config.run_axe ? "text-blue-500" : "text-muted-foreground"
              )}>
                axe-core
              </span>
              <Switch
                id="toggle-run_axe"
                checked={config.run_axe}
                onCheckedChange={(v) => update({ run_axe: v })}
                className="ml-auto scale-75 data-[state=checked]:bg-blue-500 shrink-0"
                onClick={(e) => e.stopPropagation()}
              />
            </div>
            <span className="text-[10px] text-muted-foreground leading-tight">
              DOM rules · ARIA · color contrast
            </span>
          </button>

          {/* AccessLint Engine Card */}
          <button
            type="button"
            onClick={() => update({ run_accesslint: !config.run_accesslint })}
            className={cn(
              "relative flex flex-col items-start gap-1 rounded-lg border px-3 py-2.5 text-left transition-all cursor-pointer",
              config.run_accesslint
                ? "border-purple-500/50 bg-purple-500/10 shadow-sm shadow-purple-500/10"
                : "border-border bg-card opacity-60 hover:opacity-80"
            )}
          >
            <div className="flex items-center gap-1.5 w-full">
              <div className={cn(
                "h-1.5 w-1.5 rounded-full shrink-0",
                config.run_accesslint ? "bg-purple-500" : "bg-muted-foreground/30"
              )} />
              <span className={cn(
                "text-xs font-bold uppercase tracking-wider",
                config.run_accesslint ? "text-purple-500" : "text-muted-foreground"
              )}>
                AccessLint
              </span>
              <Switch
                id="toggle-run_accesslint"
                checked={config.run_accesslint}
                onCheckedChange={(v) => update({ run_accesslint: v })}
                className="ml-auto scale-75 data-[state=checked]:bg-purple-500 shrink-0"
                onClick={(e) => e.stopPropagation()}
              />
            </div>
            <span className="text-[10px] text-muted-foreground leading-tight">
              Semantic HTML · best practices
            </span>
          </button>
        </div>
      </div>

      {/* Advanced checks — all 20 module toggles, collapsed by default */}
      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen} className="rounded-lg border border-border bg-muted/20">
        <CollapsibleTrigger className="flex w-full items-center gap-2 px-3 py-2.5 text-left">
          <SlidersHorizontal className="h-3.5 w-3.5 text-muted-foreground shrink-0" aria-hidden="true" />
          <span className="text-xs font-semibold text-foreground">{t("checks.advanced")}</span>
          <span className="text-[11px] text-muted-foreground">
            {t("checks.enabled", { n: enabledCount })}
          </span>
          <ChevronDown
            className={cn("ml-auto h-4 w-4 text-muted-foreground transition-transform", advancedOpen && "rotate-180")}
            aria-hidden="true"
          />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="border-t border-border px-3 py-3 space-y-3">
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" size="sm" className="h-6 px-2 text-[11px]" onClick={() => setAllChecks(true)}>
                {t("checks.all")}
              </Button>
              <Button type="button" variant="outline" size="sm" className="h-6 px-2 text-[11px]" onClick={() => setAllChecks(false)}>
                {t("checks.none")}
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2.5">
              {TOGGLE_ITEMS.map((item) => (
                <div key={item.key} className="flex items-center justify-between gap-2">
                  <Label
                    htmlFor={`toggle-${item.key}`}
                    className="text-xs font-medium text-muted-foreground cursor-pointer truncate"
                  >
                    {t(item.labelKey)}
                  </Label>
                  <Switch
                    id={`toggle-${item.key}`}
                    checked={config[item.key] as boolean}
                    onCheckedChange={(v) => update({ [item.key]: v } as Partial<AuditConfig>)}
                    className="scale-90 data-[state=checked]:bg-primary shrink-0"
                  />
                </div>
              ))}
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Run */}
      <Button
        onClick={handleRun}
        disabled={isRunning || !config.url}
        className={cn(
          "w-full h-11 text-sm font-semibold tracking-wider uppercase bg-primary text-primary-foreground hover:bg-primary/90 border-0",
          isRunning && "animate-amber-pulse"
        )}
      >
        {isRunning ? (
          <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
        ) : (
          <Play className="h-4 w-4 mr-2" aria-hidden="true" />
        )}
        {isRunning ? t("sidebar.running") : t("sidebar.runAudit")}
      </Button>

      {/* Status */}
      {jobStatus !== "idle" && (
        <div className="space-y-1" role="status" aria-live="polite">
          <div className="flex items-center gap-2 text-xs font-mono">
            {(jobStatus === "pending" || jobStatus === "running") && (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" aria-hidden="true" />
            )}
            {jobStatus === "completed" && (
              <CheckCircle className="h-3.5 w-3.5 text-success shrink-0" aria-hidden="true" />
            )}
            {jobStatus === "failed" && (
              <XCircle className="h-3.5 w-3.5 text-destructive shrink-0" aria-hidden="true" />
            )}
            <span className={cn(
              "capitalize",
              jobStatus === "completed" && "text-success",
              jobStatus === "failed"    && "text-destructive",
              (jobStatus === "pending" || jobStatus === "running") && "text-primary",
            )}>
              {t(STATUS_KEYS[jobStatus] ?? "status.pending")}
            </span>
          </div>
          {currentStage && (jobStatus === "pending" || jobStatus === "running") && (
            <p className="text-[11px] font-mono text-muted-foreground pl-5 truncate">
              {t((`stage.${currentStage}`) as TranslationKey) || currentStage}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
