import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Settings, Palette } from "lucide-react";
import { useLanguage } from "@/i18n/LanguageContext";

export type ThemePreference = "light" | "dark" | "system";

interface SettingsTabProps {
  maxRows: number;
  onMaxRowsChange: (value: number) => void;
  themePreference: ThemePreference;
  onThemePreferenceChange: (theme: ThemePreference) => void;
}

export function SettingsTab({
  maxRows,
  onMaxRowsChange,
  themePreference,
  onThemePreferenceChange,
}: SettingsTabProps) {
  const { t } = useLanguage();

  return (
    <div className="p-4 sm:p-6 max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Settings className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-lg font-semibold text-foreground">{t("settings.title")}</h2>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("settings.display")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-xs text-muted-foreground">{t("settings.maxRows")}</Label>
            <Input
              type="number"
              value={maxRows}
              min={10}
              max={500}
              onChange={(e) => {
                const parsed = parseInt(e.target.value, 10);
                if (Number.isNaN(parsed)) return;
                onMaxRowsChange(Math.max(10, Math.min(500, parsed)));
              }}
              className="mt-1 text-sm"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <Palette className="h-4 w-4 text-muted-foreground" />
            {t("settings.theme")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Label className="text-xs text-muted-foreground">{t("settings.colorMode")}</Label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {([
              { key: "light" as const,  labelKey: "settings.light"  as const },
              { key: "dark"  as const,  labelKey: "settings.dark"   as const },
              { key: "system" as const, labelKey: "settings.system" as const },
            ]).map((mode) => (
              <Button
                key={mode.key}
                type="button"
                variant={themePreference === mode.key ? "default" : "outline"}
                className="h-8 text-xs"
                onClick={() => onThemePreferenceChange(mode.key)}
                aria-pressed={themePreference === mode.key}
              >
                {t(mode.labelKey)}
              </Button>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground">
            {t("settings.systemNote")}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
