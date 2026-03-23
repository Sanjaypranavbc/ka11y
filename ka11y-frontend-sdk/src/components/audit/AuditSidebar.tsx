import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { AuditConfig, TabValue } from "@/types/audit";
import {
  LayoutDashboard,
  AlertTriangle,
  HelpCircle,
  CheckCircle2,
  Settings,
  Play,
  Loader2,
  CheckCircle,
  XCircle,
  X,
  Images,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface AuditSidebarProps {
  activeTab: TabValue;
  onTabChange: (tab: TabValue) => void;
  onRunAudit: (config: AuditConfig) => void;
  jobStatus: "idle" | "pending" | "running" | "completed" | "failed";
  currentStage?: string;
  open: boolean;
  onClose: () => void;
}

const navItems: { label: string; value: TabValue; icon: React.ElementType }[] = [
  { label: "Dashboard",         value: "dashboard",          icon: LayoutDashboard },
  { label: "Violations",        value: "violations",         icon: AlertTriangle   },
  { label: "Needs Review",      value: "needs-review",       icon: HelpCircle      },
  { label: "Passes",            value: "passes",             icon: CheckCircle2    },
  { label: "Image Visualiser",  value: "image-visualisation", icon: Images         },
  { label: "Settings",          value: "settings",           icon: Settings        },
];

const STAGE_LABELS: Record<string, string> = {
  axe_core:              "axe-core scan",
  image_audit:           "Image audit",
  form_audit:            "Form audit",
  label_in_name:         "Label in name",
  pause_stop_hide:       "Moving content",
  target_size:           "Target size",
  rendered_layout_audit: "Rendered layout",
};

export function AuditSidebar({ activeTab, onTabChange, onRunAudit, jobStatus, currentStage, open, onClose }: AuditSidebarProps) {
  const [config, setConfig] = useState<AuditConfig>({
    url: localStorage.getItem("ka11y_last_url") ?? "",
    max_depth: 0,
    wcag_level: "AA",
    run_ocr: true,
    run_image_audit: true,
    run_form_audit: true,
    run_label_in_name_audit: true,
    run_pause_stop_hide_audit: true,
    run_target_size_audit: true,
    run_resize_text_audit: true,
    run_reflow_audit: true,
    run_text_spacing_audit: true,
    run_orientation_audit: true,
    run_hover_focus_content_audit: true,
    run_focus_not_obscured_min_audit: true,
    run_focus_not_obscured_enh_audit: true,
  });

  const toggles: { key: keyof AuditConfig; label: string }[] = [
    { key: "run_ocr",                          label: "OCR"             },
    { key: "run_image_audit",                  label: "Image Audit"     },
    { key: "run_form_audit",                   label: "Form Audit"      },
    { key: "run_label_in_name_audit",          label: "Label in Name"   },
    { key: "run_pause_stop_hide_audit",        label: "Pause/Stop"      },
    { key: "run_target_size_audit",            label: "Target Size"     },
    { key: "run_resize_text_audit",            label: "Resize Text"     },
    { key: "run_reflow_audit",                 label: "Reflow"          },
    { key: "run_text_spacing_audit",           label: "Text Spacing"    },
    { key: "run_orientation_audit",            label: "Orientation"     },
    { key: "run_hover_focus_content_audit",    label: "Hover/Focus"     },
    { key: "run_focus_not_obscured_min_audit", label: "Focus Obscured"  },
    { key: "run_focus_not_obscured_enh_audit", label: "Focus Obscured+" },
  ];

  const isRunning = jobStatus === "pending" || jobStatus === "running";

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        aria-label="Audit controls"
        className={cn(
          "fixed top-0 left-0 z-50 h-full w-64 bg-[hsl(var(--sidebar-background))] border-r border-[hsl(var(--sidebar-border))] flex flex-col transition-transform duration-200",
          "md:translate-x-0 md:static md:z-auto",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand */}
        <div className="px-5 py-5 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-extrabold tracking-[-0.04em] text-foreground leading-none">
              ka<span className="text-primary">11</span>y
            </h1>
            <p className="text-[9px] font-mono tracking-[0.2em] uppercase text-muted-foreground mt-1 select-none">
              a11y diagnostic
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden h-7 w-7 text-muted-foreground hover:text-foreground"
            onClick={onClose}
            aria-label="Close sidebar"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>

        <Separator className="bg-[hsl(var(--sidebar-border))]" />

        {/* Navigation */}
        <nav aria-label="Main navigation" className="py-3">
          {navItems.map((item) => (
            <button
              key={item.value}
              onClick={() => { onTabChange(item.value); onClose(); }}
              aria-current={activeTab === item.value ? "page" : undefined}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-2.5 text-xs font-medium transition-colors border-l-2",
                activeTab === item.value
                  ? "border-l-primary text-primary bg-primary/5"
                  : "border-l-transparent text-muted-foreground hover:text-foreground hover:bg-black/[0.04]"
              )}
            >
              <item.icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {item.label}
            </button>
          ))}
        </nav>

        <Separator className="bg-[hsl(var(--sidebar-border))]" />

        {/* Audit Controls */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
          <p className="text-[9px] font-semibold tracking-[0.18em] uppercase text-muted-foreground">
            New Audit
          </p>

          {/* URL & depth */}
          <div className="space-y-3">
            <div>
              <Label htmlFor="audit-url" className="text-[9px] tracking-widest uppercase text-muted-foreground font-semibold">
                Target URL
              </Label>
              <Input
                id="audit-url"
                value={config.url}
                onChange={(e) => setConfig((c) => ({ ...c, url: e.target.value }))}
                placeholder="https://example.com"
                className="mt-1.5 h-8 text-xs font-mono bg-[hsl(var(--input))] border-border focus-visible:ring-primary/50"
              />
            </div>
            <div>
              <Label htmlFor="audit-max-depth" className="text-[9px] tracking-widest uppercase text-muted-foreground font-semibold">
                Max Depth
              </Label>
              <Input
                id="audit-max-depth"
                type="number"
                value={config.max_depth}
                onChange={(e) => setConfig((c) => ({ ...c, max_depth: parseInt(e.target.value) || 0 }))}
                className="mt-1.5 h-8 text-xs font-mono bg-[hsl(var(--input))] border-border focus-visible:ring-primary/50"
                min={0}
              />
            </div>
            <div>
              <Label className="text-[9px] tracking-widest uppercase text-muted-foreground font-semibold">
                WCAG Level
              </Label>
              <div className="mt-1.5 flex rounded-md overflow-hidden border border-border text-[10px] font-semibold">
                {(["A", "AA", "AAA"] as const).map((lvl) => (
                  <button
                    key={lvl}
                    type="button"
                    onClick={() => setConfig((c) => ({ ...c, wcag_level: lvl }))}
                    className={cn(
                      "flex-1 py-1.5 transition-colors",
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
          </div>

          {/* Toggles */}
          <div className="space-y-2.5">
            {toggles.map((t) => (
              <div key={t.key} className="flex items-center justify-between">
                <Label
                  htmlFor={`toggle-${t.key}`}
                  className="text-[10px] font-medium text-muted-foreground cursor-pointer"
                >
                  {t.label}
                </Label>
                <Switch
                  id={`toggle-${t.key}`}
                  checked={config[t.key] as boolean}
                  onCheckedChange={(v) => setConfig((c) => ({ ...c, [t.key]: v }))}
                  className="scale-[0.7] data-[state=checked]:bg-primary"
                />
              </div>
            ))}
          </div>

          {/* Run button */}
          <Button
            onClick={() => { localStorage.setItem("ka11y_last_url", config.url); onRunAudit(config); }}
            disabled={isRunning || !config.url}
            className={cn(
              "w-full h-9 text-xs font-semibold tracking-wider uppercase bg-primary text-primary-foreground hover:bg-primary/90 border-0",
              isRunning && "animate-amber-pulse"
            )}
          >
            {isRunning ? (
              <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" aria-hidden="true" />
            ) : (
              <Play className="h-3.5 w-3.5 mr-2" aria-hidden="true" />
            )}
            {isRunning ? "Running…" : "Run Audit"}
          </Button>

          {/* Status */}
          {jobStatus !== "idle" && (
            <div className="space-y-1" role="status" aria-live="polite">
              <div className="flex items-center gap-2 text-[10px] font-mono">
                {(jobStatus === "pending" || jobStatus === "running") && (
                  <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0" aria-hidden="true" />
                )}
                {jobStatus === "completed" && (
                  <CheckCircle className="h-3 w-3 text-success shrink-0" aria-hidden="true" />
                )}
                {jobStatus === "failed" && (
                  <XCircle className="h-3 w-3 text-destructive shrink-0" aria-hidden="true" />
                )}
                <span className={cn(
                  "capitalize",
                  jobStatus === "completed" && "text-success",
                  jobStatus === "failed"    && "text-destructive",
                  (jobStatus === "pending" || jobStatus === "running") && "text-primary",
                )}>
                  {jobStatus}
                </span>
              </div>
              {currentStage && (jobStatus === "pending" || jobStatus === "running") && (
                <p className="text-[9px] font-mono text-muted-foreground pl-5 truncate">
                  {STAGE_LABELS[currentStage] ?? currentStage}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer rule */}
        <div className="px-4 py-3 border-t border-[hsl(var(--sidebar-border))]">
          <p className="text-[8px] font-mono tracking-widest text-muted-foreground/40 uppercase">
            WCAG 2.1 A / AA / AAA · axe-core + Python
          </p>
        </div>
      </aside>
    </>
  );
}