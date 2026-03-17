import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, Image as ImageIcon, FileCheck } from "lucide-react";

export const KeyHighlights = () => {
  const highlights = [
    {
      title: "Missing Image Descriptions",
      description: "12 images don't have descriptions, making them invisible to screen readers",
      whyItMatters: "People using screen readers can't understand what these images show",
      action: "Add descriptive alt text to each image",
      icon: ImageIcon,
      severity: "critical",
    },
    {
      title: "Hard to Read Buttons",
      description: "Your call-to-action buttons don't have enough color contrast",
      whyItMatters: "Users with low vision or color blindness may not be able to read them",
      action: "Increase the contrast between button text and background colors",
      icon: TrendingUp,
      severity: "serious",
    },
    {
      title: "Unclear Navigation",
      description: "Navigation menu items are missing clear labels",
      whyItMatters: "Screen reader users may not understand where each link goes",
      action: "Add descriptive ARIA labels to navigation items",
      icon: FileCheck,
      severity: "moderate",
    },
  ];

  const getSeverityColor = (severity: string) => {
    const colors: Record<string, string> = {
      critical: "bg-critical text-critical-foreground",
      serious: "bg-serious text-serious-foreground",
      moderate: "bg-moderate text-moderate-foreground",
    };
    return colors[severity] || "bg-minor text-minor-foreground";
  };

  return (
    <section className="space-y-6">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-foreground mb-2">
          Top Issues You Should Fix First
        </h2>
        <p className="text-muted-foreground text-lg">
          These are the most important things to address
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {highlights.map((highlight, index) => (
          <Card key={index} className="p-6 hover:shadow-md transition-all border-2">
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                <div className={`h-12 w-12 rounded-xl flex items-center justify-center flex-shrink-0 ${
                  highlight.severity === 'critical' ? 'bg-critical/10' :
                  highlight.severity === 'serious' ? 'bg-serious/10' :
                  'bg-moderate/10'
                }`}>
                  <highlight.icon className={`h-6 w-6 ${
                    highlight.severity === 'critical' ? 'text-critical' :
                    highlight.severity === 'serious' ? 'text-serious' :
                    'text-moderate'
                  }`} />
                </div>
                <Badge className={getSeverityColor(highlight.severity)}>
                  {highlight.severity}
                </Badge>
              </div>

              <div>
                <h3 className="font-bold text-lg text-foreground mb-2">
                  {highlight.title}
                </h3>
                <p className="text-sm text-foreground mb-3">
                  {highlight.description}
                </p>
                
                <div className="p-3 rounded-lg bg-muted border border-border">
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    Why it matters:
                  </p>
                  <p className="text-sm text-foreground">
                    {highlight.whyItMatters}
                  </p>
                </div>
              </div>

              <div className="pt-3 border-t border-border">
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Recommended action:
                </p>
                <p className="text-sm font-medium text-primary">
                  {highlight.action}
                </p>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
};
