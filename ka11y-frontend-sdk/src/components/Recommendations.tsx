import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { ChevronRight, Code2 } from "lucide-react";

export const Recommendations = () => {
  const recommendations = [
    {
      category: "Make Text Easier to Read",
      icon: "📖",
      items: [
        {
          title: "Increase Text Contrast",
          description:
            "Some text is hard to read because it doesn't stand out enough from the background",
          whatToDo: "Use darker text colors on light backgrounds, or lighter text on dark backgrounds",
          priority: "High",
          technicalNote: "Aim for a contrast ratio of at least 4.5:1 (WCAG 1.4.3)",
          codeSnippet: `/* Good contrast example */
.text {
  background-color: #FFFFFF;
  color: #1a1a1a;
  /* Contrast ratio: 16:1 ✓ */
}`,
        },
        {
          title: "Make Font Sizes Larger",
          description:
            "Some text might be too small for users to read comfortably",
          whatToDo: "Use at least 16px for body text and larger sizes for headings",
          priority: "Medium",
          technicalNote: "Body text should be at least 16px (1rem)",
        },
      ],
    },
    {
      category: "Improve Page Structure",
      icon: "🏗️",
      items: [
        {
          title: "Add Clear Headings",
          description:
            "Your page structure could be clearer with better organized headings",
          whatToDo: "Use headings (like titles and subtitles) in the right order to organize your content",
          priority: "Medium",
          technicalNote: "Use proper heading hierarchy (h1, h2, h3) - WCAG 1.3.1",
        },
      ],
    },
    {
      category: "Fix Broken or Missing Labels",
      icon: "🏷️",
      items: [
        {
          title: "Add Labels to Form Fields",
          description:
            "Some form fields don't have clear labels, making it unclear what information to enter",
          whatToDo: "Add a descriptive label above or next to each input field",
          priority: "High",
          technicalNote: "All form inputs must have associated labels - WCAG 3.3.2",
          codeSnippet: `<label for="email">Email address</label>
<input type="email" id="email" name="email">`,
        },
        {
          title: "Describe Icon Buttons",
          description:
            "Buttons with only icons don't tell screen reader users what they do",
          whatToDo: "Add hidden text descriptions to icon-only buttons",
          priority: "High",
          technicalNote: "Use aria-label for icon buttons - WCAG 4.1.2",
        },
      ],
    },
    {
      category: "Improve Navigation and Keyboard Access",
      icon: "⌨️",
      items: [
        {
          title: "Show Focus Indicators",
          description:
            "It's hard to see which element is selected when using keyboard navigation",
          whatToDo: "Add a visible outline or highlight when someone tabs through your page",
          priority: "Medium",
          technicalNote: "All interactive elements need visible focus indicators - WCAG 2.4.7",
        },
      ],
    },
    {
      category: "Improve Image Descriptions",
      icon: "🖼️",
      items: [
        {
          title: "Add Alt Text to Images",
          description:
            "Many images don't have descriptions, so screen reader users can't tell what they show",
          whatToDo: "Write a brief description of each image's content or purpose",
          priority: "High",
          technicalNote: "All meaningful images must have alt attributes - WCAG 1.1.1",
          codeSnippet: `<img 
  src="product.jpg" 
  alt="Red wireless headphones on white background"
>`,
        },
      ],
    },
  ];

  return (
    <section className="space-y-6">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-foreground mb-2">
          Recommended Fixes for Your Website
        </h2>
        <p className="text-muted-foreground text-lg">
          Here's how to fix each issue, explained in simple terms
        </p>
      </div>

      <Accordion type="single" collapsible className="space-y-4">
        {recommendations.map((category, index) => (
          <AccordionItem
            key={index}
            value={`category-${index}`}
            className="border-2 rounded-xl px-6 bg-card shadow-sm"
          >
            <AccordionTrigger className="hover:no-underline py-5">
              <div className="flex items-center gap-4">
                <div className="text-3xl">{category.icon}</div>
                <div className="text-left">
                  <h3 className="font-bold text-lg text-foreground">
                    {category.category}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {category.items.length} {category.items.length === 1 ? "fix" : "fixes"} to make
                  </p>
                </div>
              </div>
            </AccordionTrigger>

            <AccordionContent className="space-y-4 pt-4 pb-4">
              {category.items.map((item, itemIndex) => (
                <Card key={itemIndex} className="p-5 border-2">
                  <div className="space-y-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <Badge
                            variant={
                              item.priority === "High" ? "destructive" : "secondary"
                            }
                            className="font-medium"
                          >
                            {item.priority} Priority
                          </Badge>
                        </div>
                        <h4 className="font-bold text-lg text-foreground mb-2">
                          {item.title}
                        </h4>
                        <p className="text-foreground mb-3">
                          {item.description}
                        </p>
                        
                        <div className="p-4 rounded-lg bg-primary/5 border border-primary/20">
                          <p className="text-sm font-semibold text-foreground mb-1">
                            What to do:
                          </p>
                          <p className="text-sm text-foreground">
                            {item.whatToDo}
                          </p>
                        </div>
                      </div>
                    </div>

                    <details className="group">
                      <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground flex items-center gap-2 p-2 rounded hover:bg-muted/50 transition-colors">
                        <ChevronRight className="h-4 w-4 transition-transform group-open:rotate-90" />
                        Show technical details
                      </summary>
                      <div className="mt-3 p-4 rounded-lg bg-muted/50 space-y-3">
                        <p className="text-sm text-muted-foreground">
                          {item.technicalNote}
                        </p>
                        {item.codeSnippet && (
                          <div>
                            <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-2">
                              <Code2 className="h-4 w-4" />
                              Code example:
                            </p>
                            <pre className="p-3 rounded-md bg-background overflow-x-auto text-xs border">
                              <code>{item.codeSnippet}</code>
                            </pre>
                          </div>
                        )}
                      </div>
                    </details>
                  </div>
                </Card>
              ))}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </section>
  );
};
