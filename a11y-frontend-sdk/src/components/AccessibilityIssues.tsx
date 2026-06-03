import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChevronDown, Code2, MapPin } from "lucide-react";

interface Issue {
  id: string;
  severity: "critical" | "serious" | "moderate" | "minor";
  wcagRule: string;
  title: string;
  description: string;
  domPath: string;
  fix: string;
  codeSnippet?: string;
}

const mockIssues: Issue[] = [
  {
    id: "1",
    severity: "critical",
    wcagRule: "WCAG 1.1.1",
    title: "Images missing alt text",
    description: "12 images on the page do not have alternative text, making them inaccessible to screen reader users.",
    domPath: "body > main > section.hero > img",
    fix: "Add descriptive alt attributes to all images. For decorative images, use alt=\"\".",
    codeSnippet: '<img src="hero.jpg" alt="Team collaboration in modern office" />',
  },
  {
    id: "2",
    severity: "serious",
    wcagRule: "WCAG 1.4.3",
    title: "Insufficient color contrast",
    description: "Text on primary buttons has a contrast ratio of 3.2:1, below the required 4.5:1 minimum.",
    domPath: "body > header > nav > button.cta",
    fix: "Increase contrast by darkening the button background or lightening the text color.",
    codeSnippet: "background: #2563eb; color: #ffffff; /* 7.5:1 ratio */",
  },
  {
    id: "3",
    severity: "moderate",
    wcagRule: "WCAG 4.1.2",
    title: "Missing ARIA labels on navigation",
    description: "Navigation menu items lack proper ARIA labels for assistive technologies.",
    domPath: "body > header > nav > ul",
    fix: "Add aria-label or aria-labelledby attributes to navigation elements.",
    codeSnippet: '<nav aria-label="Main navigation">',
  },
  {
    id: "4",
    severity: "minor",
    wcagRule: "WCAG 2.4.4",
    title: "Link purpose unclear",
    description: "Several 'Read more' links don't provide context about their destination.",
    domPath: "body > main > article > a.read-more",
    fix: "Make link text more descriptive or add aria-label with context.",
    codeSnippet: '<a href="/article">Read more about accessibility best practices</a>',
  },
];

export const AccessibilityIssues = () => {
  const [severityFilter, setSeverityFilter] = useState("all");
  const [sortBy, setSortBy] = useState("severity");

  const filteredIssues = mockIssues.filter(
    (issue) => severityFilter === "all" || issue.severity === severityFilter
  );

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
      <div className="text-center mb-6">
        <h2 className="text-3xl font-bold text-foreground mb-2">
          All Accessibility Issues
        </h2>
        <p className="text-muted-foreground text-lg">
          A complete list of everything we found, organized for easy review
        </p>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">
            {filteredIssues.length} {filteredIssues.length === 1 ? "issue" : "issues"} found
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Select value={severityFilter} onValueChange={setSeverityFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Filter by severity" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Severities</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="serious">Serious</SelectItem>
              <SelectItem value="moderate">Moderate</SelectItem>
              <SelectItem value="minor">Minor</SelectItem>
            </SelectContent>
          </Select>

          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Sort by" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="severity">Severity</SelectItem>
              <SelectItem value="rule">WCAG Rule</SelectItem>
              <SelectItem value="element">Element</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-4">
        {filteredIssues.map((issue) => (
          <Collapsible key={issue.id}>
            <Card className="overflow-hidden">
              <CollapsibleTrigger asChild>
                <Button
                  variant="ghost"
                  className="w-full p-6 h-auto hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start gap-4 w-full text-left">
                    <Badge className={`${getSeverityColor(issue.severity)} mt-1`}>
                      {issue.severity}
                    </Badge>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <Badge variant="outline">{issue.wcagRule}</Badge>
                        <h3 className="font-semibold text-foreground">
                          {issue.title}
                        </h3>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {issue.description}
                      </p>
                    </div>
                    <ChevronDown className="h-5 w-5 text-muted-foreground transition-transform duration-200" />
                  </div>
                </Button>
              </CollapsibleTrigger>

              <CollapsibleContent>
                <div className="px-6 pb-6 space-y-4 border-t border-border pt-4">
                  <div className="flex items-start gap-2">
                    <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <div className="text-xs font-medium text-muted-foreground uppercase mb-1">
                        DOM Location
                      </div>
                      <code className="text-sm bg-muted px-2 py-1 rounded">
                        {issue.domPath}
                      </code>
                    </div>
                  </div>

                  <div className="bg-accent/50 p-4 rounded-lg">
                    <div className="text-sm font-medium mb-2 flex items-center gap-2">
                      <span>✓</span> Recommended Fix
                    </div>
                    <p className="text-sm text-muted-foreground">{issue.fix}</p>
                  </div>

                  {issue.codeSnippet && (
                    <div>
                      <div className="text-xs font-medium text-muted-foreground uppercase mb-2 flex items-center gap-2">
                        <Code2 className="h-3 w-3" />
                        Code Example
                      </div>
                      <pre className="bg-muted p-3 rounded text-xs overflow-x-auto">
                        <code>{issue.codeSnippet}</code>
                      </pre>
                    </div>
                  )}
                </div>
              </CollapsibleContent>
            </Card>
          </Collapsible>
        ))}
      </div>
    </section>
  );
};
