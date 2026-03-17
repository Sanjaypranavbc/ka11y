import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertCircle, Eye } from "lucide-react";

export const OcrFindings = () => {
  const findings = [
    {
      id: "1",
      text: "Contact Us",
      issue: "Low contrast ratio (2.8:1)",
      location: "Footer section",
      recommendation: "Increase contrast to at least 4.5:1 for normal text",
      severity: "serious",
    },
    {
      id: "2",
      text: "Sign Up Now",
      issue: "Text partially obscured by background image",
      location: "Hero CTA button",
      recommendation: "Add semi-transparent overlay behind text or adjust background",
      severity: "moderate",
    },
    {
      id: "3",
      text: "Learn More →",
      issue: "Missing text alternative for arrow symbol",
      location: "Feature cards",
      recommendation: "Include symbol meaning in accessible name",
      severity: "minor",
    },
  ];

  const getSeverityColor = (severity: string) => {
    const colors: Record<string, string> = {
      critical: "bg-critical text-critical-foreground",
      serious: "bg-serious text-serious-foreground",
      moderate: "bg-moderate text-moderate-foreground",
      minor: "bg-minor text-minor-foreground",
    };
    return colors[severity] || "bg-minor text-minor-foreground";
  };

  return (
    <section className="space-y-6">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-foreground mb-2">
          Text Readability Issues
        </h2>
        <p className="text-muted-foreground text-lg">
          Problems we found with text that might be hard to read
        </p>
      </div>

      <div className="space-y-4">
        {findings.map((finding) => (
          <Card key={finding.id} className="p-6">
            <div className="flex items-start gap-4">
              <div className="h-10 w-10 rounded-lg bg-accent flex items-center justify-center flex-shrink-0">
                <Eye className="h-5 w-5 text-accent-foreground" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-3">
                  <Badge className={getSeverityColor(finding.severity)}>
                    {finding.severity}
                  </Badge>
                  <code className="text-sm bg-muted px-2 py-1 rounded">
                    {finding.text}
                  </code>
                </div>

                <div className="space-y-3">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <div className="text-sm font-medium mb-1">Issue</div>
                      <p className="text-sm text-muted-foreground">
                        {finding.issue}
                      </p>
                    </div>
                  </div>

                  <div className="text-xs text-muted-foreground">
                    Location: {finding.location}
                  </div>

                  <div className="bg-accent/50 p-3 rounded-lg">
                    <div className="text-sm font-medium mb-1">
                      ✓ Recommendation
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {finding.recommendation}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
};
