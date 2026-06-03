import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { TabValue } from "@/types/audit";
import {
  LayoutDashboard,
  AlertTriangle,
  HelpCircle,
  CheckCircle2,
  Settings,
  Plus,
  X,
  Images,
  BookOpen,
  Beaker,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/i18n/LanguageContext";
import { TranslationKey } from "@/i18n/translations";

interface AuditSidebarProps {
  activeTab: TabValue;
  onTabChange: (tab: TabValue) => void;
  onNewAudit: () => void;
  open: boolean;
  onClose: () => void;
}

const NAV_ITEMS: { key: TranslationKey; value: TabValue; icon: React.ElementType }[] = [
  { key: "nav.dashboard",       value: "dashboard",           icon: LayoutDashboard },
  { key: "nav.violations",      value: "violations",          icon: AlertTriangle   },
  { key: "nav.needsReview",     value: "needs-review",        icon: HelpCircle      },
  { key: "nav.passes",          value: "passes",              icon: CheckCircle2    },
  { key: "nav.imageVisualiser", value: "image-visualisation", icon: Images          },
  { key: "nav.wcagRules",       value: "wcag-rules",          icon: BookOpen        },
  { key: "nav.ruleEvaluator",   value: "rule-evaluator",      icon: Beaker          },
  { key: "nav.settings",        value: "settings",            icon: Settings        },
];

export function AuditSidebar({ activeTab, onTabChange, onNewAudit, open, onClose }: AuditSidebarProps) {
  const { t } = useLanguage();

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-40 cursor-pointer bg-background/80 backdrop-blur-sm md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        aria-label={t("sidebar.ariaLabel")}
        className={cn(
          "fixed top-0 left-0 z-50 h-full w-[78vw] max-w-72 md:w-60 bg-[hsl(var(--sidebar-background))] border-r border-[hsl(var(--sidebar-border))] flex flex-col transition-transform duration-200",
          "md:translate-x-0 md:static md:z-auto",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand */}
        <div className="px-5 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="h-9 w-9 shrink-0 rounded-xl bg-gradient-to-br from-indigo-500 via-primary to-emerald-400 shadow-sm"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <h1 className="text-xl font-extrabold tracking-[-0.04em] text-foreground leading-none">
                <span className="text-primary">A11y</span>
              </h1>
              <p className="text-[9px] font-mono tracking-[0.2em] uppercase text-muted-foreground mt-1 select-none">
                {t("sidebar.tagline")}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden h-7 w-7 text-muted-foreground hover:text-foreground"
            onClick={onClose}
            aria-label={t("sidebar.closeSidebar")}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>

        <div className="px-4">
          <Button
            onClick={() => { onNewAudit(); onClose(); }}
            className="w-full h-10 text-sm font-semibold tracking-wide bg-primary text-primary-foreground hover:bg-primary/90 border-0"
          >
            <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
            {t("sidebar.newAudit")}
          </Button>
        </div>

        <Separator className="my-3 bg-[hsl(var(--sidebar-border))]" />

        {/* Navigation */}
        <nav aria-label={t("sidebar.navAriaLabel")} className="flex-1 overflow-y-auto py-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.value}
              onClick={() => { onTabChange(item.value); onClose(); }}
              aria-current={activeTab === item.value ? "page" : undefined}
              className={cn(
                "w-full cursor-pointer flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors border-l-2",
                activeTab === item.value
                  ? "border-l-primary text-primary bg-primary/5"
                  : "border-l-transparent text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04]"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {t(item.key)}
            </button>
          ))}
        </nav>

        {/* Footer rule */}
        <div className="px-4 py-3 border-t border-[hsl(var(--sidebar-border))]">
          <p className="text-[9px] font-mono tracking-widest text-muted-foreground/50 uppercase">
            {t("sidebar.footer")}
          </p>
        </div>
      </aside>
    </>
  );
}
