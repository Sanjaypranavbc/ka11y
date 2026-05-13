import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Loader2, Play, AlertCircle, CheckCircle, HelpCircle, XCircle, Download } from "lucide-react";
import { useLanguage } from "@/i18n/LanguageContext";
import { cn } from "@/lib/utils";

interface Finding {
  rule_id: string;
  wcag_sc: string;
  status: "pass" | "fail" | "needs_review";
  reason: string;
  element?: {
    selector?: string;
    html?: string;
  };
}

interface TestResponse {
  status: string;
  findings: Finding[];
}

export function RuleEvaluatorTab() {
  const { t, lang } = useLanguage();
  const [url, setUrl] = useState(localStorage.getItem("ka11y_last_url") || "");
  const [ruleId, setRuleId] = useState("wcag_1_2_2");
  const [forceRefresh, setForceRefresh] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Finding[] | null>(null);

  const handleTest = async () => {
    if (!url) return;
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const response = await fetch("/api/v1/test/rule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          rule_id: ruleId,
          force_refresh: forceRefresh,
          language: lang,
        }),
      });

      if (!response.ok) {
        const errDetails = await response.text();
        throw new Error(`Server err: ${response.status} - ${errDetails}`);
      }

      const data = (await response.json()) as TestResponse;
      setResults(data.findings || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Test failed to run.");
    } finally {
      setLoading(false);
    }
  };

  const handleExport = () => {
    if (!results) return;
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(results, null, 2));
    const a = document.createElement("a");
    a.href = dataStr;
    a.download = `${ruleId}_evaluation_report.json`;
    a.click();
  };

  return (
    <div className="p-3 sm:p-5 space-y-4 max-w-4xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Individual Rule Tester</h2>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            Select an individual accessibility rule to test exclusively against your target URL.
          </p>
        </div>
      </div>

      <div className="border border-border p-4 rounded-md space-y-4 bg-card">
        <div className="space-y-3">
          <div className="grid gap-2">
            <Label htmlFor="test-url" className="text-xs font-semibold">Target URL</Label>
            <Input
              id="test-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              className="font-mono text-xs max-w-lg"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="test-rule" className="text-xs font-semibold">Select Rule</Label>
            <select
              id="test-rule"
              value={ruleId}
              onChange={(e) => setRuleId(e.target.value)}
              className="flex h-9 w-full max-w-sm rounded-md border border-border bg-input px-3 py-1 text-xs shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
            >
              <optgroup label="Audio & Video">
                <option value="wcag_1_2_1">WCAG 1.2.1 Audio-only/Video-only</option>
                <option value="wcag_1_2_2">WCAG 1.2.2 Captions (Prerecorded)</option>
              </optgroup>
              <optgroup label="Images & Text Alternatives">
                <option value="wcag_1_1_1">WCAG 1.1.1 Non-text Content</option>
                <option value="wcag_1_4_5">WCAG 1.4.5 Images of Text</option>
                <option value="wcag_1_4_11">WCAG 1.4.11 Non-text Contrast</option>
                <option value="wcag_4_1_2">WCAG 4.1.2 Name, Role, Value</option>
                <option value="wcag_1_4_3">WCAG 1.4.3 Contrast (Minimum)</option>
                <option value="wcag_1_4_6">WCAG 1.4.6 Contrast (Enhanced)</option>
              </optgroup>
              <optgroup label="Forms & Inputs">
                <option value="wcag_3_3_1">WCAG 3.3.1 Error Identification</option>
                <option value="wcag_3_3_2">WCAG 3.3.2 Labels or Instructions</option>
                <option value="wcag_1_3_1_form">WCAG 1.3.1 Form Relationships</option>
                <option value="wcag_2_5_3">WCAG 2.5.3 Label in Name</option>
              </optgroup>
              <optgroup label="Layout, Sizing & Motion">
                <option value="wcag_2_2_2">WCAG 2.2.2 Pause, Stop, Hide</option>
                <option value="wcag_2_5_8">WCAG 2.5.8 Target Size (Minimum)</option>
                <option value="wcag_1_4_12">WCAG 1.4.12 Text Spacing</option>
                <option value="wcag_1_3_3">WCAG 1.3.3 Sensory Characteristics</option>
              </optgroup>
              <optgroup label="Viewport & Rendering">
                <option value="wcag_1_4_4">WCAG 1.4.4 Resize Text</option>
                <option value="wcag_1_4_10">WCAG 1.4.10 Reflow</option>
                <option value="wcag_1_3_4">WCAG 1.3.4 Orientation</option>
                <option value="wcag_1_4_13">WCAG 1.4.13 Content on Hover or Focus</option>
                <option value="wcag_2_4_11">WCAG 2.4.11 Focus Not Obscured (Min)</option>
                <option value="wcag_2_4_12">WCAG 2.4.12 Focus Not Obscured (Enh)</option>
              </optgroup>
              <optgroup label="Standard Javascript Engines">
                <option value="axe_core">All Axe-Core Rules (Live Render)</option>
              </optgroup>
            </select>
          </div>

          <div className="flex items-center space-x-3 py-2">
            <Switch
              id="test-force"
              checked={forceRefresh}
              onCheckedChange={setForceRefresh}
            />
            <Label htmlFor="test-force" className="text-xs text-muted-foreground">Force Snapshot Refresh</Label>
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={handleTest} disabled={loading || !url} size="sm" className="w-32">
              {loading ? <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" /> : <Play className="h-3.5 w-3.5 mr-2" />}
              {loading ? "Evaluating..." : "Evaluate Rule"}
            </Button>
            {results && (
              <Button onClick={handleExport} variant="outline" size="sm">
                <Download className="h-3.5 w-3.5 mr-2" />
                Export JSON
              </Button>
            )}
          </div>
        </div>
      </div>

      <div className="pt-4">
        {error && (
          <div className="flex items-center gap-2 px-4 py-3 rounded border border-destructive/30 bg-destructive/5 text-destructive text-xs">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {results && (
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Findings ({results.length})</h3>
            {results.length === 0 ? (
              <div className="px-4 py-8 border border-dashed rounded flex flex-col items-center justify-center text-muted-foreground">
                <CheckCircle className="h-8 w-8 mb-2 opacity-50" />
                <p className="text-xs">Rule passed. No findings reported for this rule.</p>
              </div>
            ) : (
              results.map((r, i) => (
                <div key={i} className="border border-border p-3 rounded bg-card text-xs space-y-2">
                  <div className="flex items-center gap-2">
                    {r.status === "fail" && <XCircle className="h-4 w-4 text-destructive" />}
                    {r.status === "needs_review" && <HelpCircle className="h-4 w-4 text-orange-500" />}
                    {r.status === "pass" && <CheckCircle className="h-4 w-4 text-success" />}
                    <span className="font-semibold">{r.rule_id}</span>
                  </div>
                  <p className="text-muted-foreground">{r.reason}</p>
                  {r.element?.html && (
                    <pre className="mt-2 p-2 bg-muted/30 border text-[10px] rounded overflow-x-auto text-muted-foreground font-mono">
                      {r.element.html}
                    </pre>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
