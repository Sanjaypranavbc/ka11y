import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Settings } from "lucide-react";

interface SettingsTabProps {
  maxRows: number;
  onMaxRowsChange: (value: number) => void;
}

export function SettingsTab({ maxRows, onMaxRowsChange }: SettingsTabProps) {
  return (
    <div className="p-6 max-w-2xl space-y-6">
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
    </div>
  );
}
