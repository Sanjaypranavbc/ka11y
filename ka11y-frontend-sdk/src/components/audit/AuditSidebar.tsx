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
} from "lucide-react";
import { cn } from "@/lib/utils";

interface AuditSidebarProps {
  activeTab: TabValue;
  onTabChange: (tab: TabValue) => void;
  onRunAudit: (config: AuditConfig) => void;
  jobStatus: "idle" | "pending" | "running" | "completed" | "failed";
  open: boolean;
  onClose: () => void;
}

const navItems: { label: string; value: TabValue; icon: React.ElementType }[] = [
  { label: "Dashboard", value: "dashboard", icon: LayoutDashboard },
  { label: "Violations", value: "violations", icon: AlertTriangle },
  { label: "Needs Review", value: "needs-review", icon: HelpCircle },
  { label: "Passes", value: "passes", icon: CheckCircle2 },
  { label: "Settings", value: "settings", icon: Settings },
];

export function AuditSidebar({ activeTab, onTabChange, onRunAudit, jobStatus, open, onClose }: AuditSidebarProps) {
  const [config, setConfig] = useState<AuditConfig>({
    url: "https://www.kao.com/global/en/",
    max_depth: 0,
    run_ocr: true,
    run_image_audit: true,
    run_form_audit: true,
    run_label_in_name_audit: true,
    run_pause_stop_hide_audit: true,
    run_target_size_audit: true,
  });

  const toggles: { key: keyof AuditConfig; label: string }[] = [
    { key: "run_ocr", label: "OCR" },
    { key: "run_image_audit", label: "Image Audit" },
    { key: "run_form_audit", label: "Form Audit" },
    { key: "run_label_in_name_audit", label: "Label in Name" },
    { key: "run_pause_stop_hide_audit", label: "Pause/Stop/Hide" },
    { key: "run_target_size_audit", label: "Target Size" },
  ];

  const isRunning = jobStatus === "pending" || jobStatus === "running";

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div className="fixed inset-0 z-40 bg-foreground/20 md:hidden" onClick={onClose} />
      )}

      <aside
        className={cn(
          "fixed top-0 left-0 z-50 h-full w-72 bg-card border-r border-border flex flex-col transition-transform duration-200",
          "md:translate-x-0 md:static md:z-auto",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Header */}
        <div className="p-5 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground tracking-tight">ka11y</h1>
            <p className="text-xs text-muted-foreground">Accessibility Auditor</p>
          </div>
          <Button variant="ghost" size="icon" className="md:hidden" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <Separator />

        {/* Navigation */}
        <nav className="p-3 space-y-1">
          {navItems.map((item) => (
            <button
              key={item.value}
              onClick={() => { onTabChange(item.value); onClose(); }}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                activeTab === item.value
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </button>
          ))}
        </nav>

        <Separator />

        {/* Audit Controls */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <h3 className="text-sm font-semibold text-foreground">Run New Audit</h3>

          <div className="space-y-3">
            <div>
              <Label className="text-xs text-muted-foreground">URL to audit</Label>
              <Input
                value={config.url}
                onChange={(e) => setConfig((c) => ({ ...c, url: e.target.value }))}
                placeholder="https://example.com"
                className="mt-1 text-xs h-8"
              />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Max depth</Label>
              <Input
                type="number"
                value={config.max_depth}
                onChange={(e) => setConfig((c) => ({ ...c, max_depth: parseInt(e.target.value) || 0 }))}
                className="mt-1 text-xs h-8"
                min={0}
              />
            </div>
          </div>

          <div className="space-y-2">
            {toggles.map((t) => (
              <div key={t.key} className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">{t.label}</Label>
                <Switch
                  checked={config[t.key] as boolean}
                  onCheckedChange={(v) => setConfig((c) => ({ ...c, [t.key]: v }))}
                  className="scale-75"
                />
              </div>
            ))}
          </div>

          <Button
            onClick={() => onRunAudit(config)}
            disabled={isRunning || !config.url}
            className="w-full"
          >
            {isRunning ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            {isRunning ? "Running..." : "Run Audit"}
          </Button>

          {/* Status indicator */}
          {jobStatus !== "idle" && (
            <div className="flex items-center gap-2 text-xs">
              {jobStatus === "pending" && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
              {jobStatus === "running" && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
              {jobStatus === "completed" && <CheckCircle className="h-3 w-3 text-success" />}
              {jobStatus === "failed" && <XCircle className="h-3 w-3 text-destructive" />}
              <span className="text-muted-foreground capitalize">{jobStatus}</span>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
