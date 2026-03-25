import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Settings, Palette } from "lucide-react";

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
  return (
    <div className="p-4 sm:p-6 max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Settings className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-lg font-semibold text-foreground">Settings</h2>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Display</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-xs text-muted-foreground">Max rows per table</Label>
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
            Theme
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Label className="text-xs text-muted-foreground">Color mode</Label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {([
              { key: "light", label: "Light" },
              { key: "dark", label: "Dark" },
              { key: "system", label: "System" },
            ] as const).map((mode) => (
              <Button
                key={mode.key}
                type="button"
                variant={themePreference === mode.key ? "default" : "outline"}
                className="h-8 text-xs"
                onClick={() => onThemePreferenceChange(mode.key)}
                aria-pressed={themePreference === mode.key}
              >
                {mode.label}
              </Button>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground">
            System mode follows your device preference.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
