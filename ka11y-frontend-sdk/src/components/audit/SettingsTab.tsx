import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Settings } from "lucide-react";

export function SettingsTab() {
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
            <Input type="number" defaultValue={50} className="mt-1 text-sm" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
