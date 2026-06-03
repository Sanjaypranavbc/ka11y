import { AlertTriangle, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface HeroSummaryProps {
  score: number;
  totalIssues: number;
  criticalCount: number;
  seriousCount: number;
  moderateCount: number;
  minorCount: number;
  wcagVersion: string;
  wcagLevel: string;
}

export const HeroSummary = ({
  score,
  totalIssues,
  criticalCount,
  seriousCount,
  moderateCount,
  minorCount,
  wcagVersion,
  wcagLevel,
}: HeroSummaryProps) => {
  const getScoreColor = (score: number) => {
    if (score >= 80) return "text-success";
    if (score >= 60) return "text-moderate";
    return "text-critical";
  };

  const getScoreLabel = (score: number) => {
    if (score >= 80) return "Excellent";
    if (score >= 60) return "Good";
    return "Needs Improvement";
  };

  return (
    <Card className="p-8 shadow-sm border-2">
      <div className="text-center mb-8">
        <h2 className="text-2xl font-bold text-foreground mb-2">
          At a Glance
        </h2>
        <p className="text-muted-foreground">
          Below is a detailed breakdown of everything we found and how to fix them.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="flex flex-col items-center justify-center lg:border-r border-border">
          <div className="text-center">
            <div className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Accessibility Score
            </div>
            <div className={`text-7xl font-bold ${getScoreColor(score)} mb-2`}>
              {score}
            </div>
            <div className="text-xl font-semibold text-muted-foreground mb-3">
              out of 100
            </div>
            <Badge variant="outline" className="text-base px-4 py-1">
              {getScoreLabel(score)}
            </Badge>
          </div>
        </div>

        <div className="lg:col-span-2 space-y-6">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground">
                Total Issues Found
              </h3>
              <span className="text-3xl font-bold text-foreground">{totalIssues}</span>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center gap-3 p-3 rounded-lg bg-critical/5 border border-critical/20">
                <div className="h-10 w-10 rounded-lg bg-critical/10 flex items-center justify-center flex-shrink-0">
                  <XCircle className="h-5 w-5 text-critical" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-foreground">{criticalCount}</div>
                  <div className="text-xs font-medium text-critical">Critical</div>
                </div>
              </div>

              <div className="flex items-center gap-3 p-3 rounded-lg bg-serious/5 border border-serious/20">
                <div className="h-10 w-10 rounded-lg bg-serious/10 flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="h-5 w-5 text-serious" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-foreground">{seriousCount}</div>
                  <div className="text-xs font-medium text-serious">Serious</div>
                </div>
              </div>

              <div className="flex items-center gap-3 p-3 rounded-lg bg-moderate/5 border border-moderate/20">
                <div className="h-10 w-10 rounded-lg bg-moderate/10 flex items-center justify-center flex-shrink-0">
                  <AlertCircle className="h-5 w-5 text-moderate" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-foreground">{moderateCount}</div>
                  <div className="text-xs font-medium text-moderate">Moderate</div>
                </div>
              </div>

              <div className="flex items-center gap-3 p-3 rounded-lg bg-minor/5 border border-minor/20">
                <div className="h-10 w-10 rounded-lg bg-minor/10 flex items-center justify-center flex-shrink-0">
                  <CheckCircle2 className="h-5 w-5 text-minor" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-foreground">{minorCount}</div>
                  <div className="text-xs font-medium text-minor">Minor</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
};
