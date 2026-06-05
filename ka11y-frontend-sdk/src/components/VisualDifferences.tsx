import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const VisualDifferences = () => {
  const differences = [
    {
      id: "1",
      component: "Navigation Header",
      mismatchPercentage: 12.4,
      description: "Layout shift detected in mobile navigation menu",
    },
    {
      id: "2",
      component: "Hero Section",
      mismatchPercentage: 5.8,
      description: "Button positioning changed across viewport sizes",
    },
    {
      id: "3",
      component: "Footer",
      mismatchPercentage: 3.2,
      description: "Minor spacing differences in social media icons",
    },
  ];

  return (
    <section className="space-y-6">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-foreground mb-2">
          Visual Changes Detected
        </h2>
        <p className="text-muted-foreground text-lg">
          Here's how your page looks compared to its original version
        </p>
      </div>

      <div className="space-y-6">
        {differences.map((diff) => (
          <Card key={diff.id} className="overflow-hidden">
            <div className="p-6 bg-muted/30">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-semibold text-foreground mb-1">
                    {diff.component}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {diff.description}
                  </p>
                </div>
                <Badge variant="outline" className="ml-4">
                  {diff.mismatchPercentage}% diff
                </Badge>
              </div>

              <Tabs defaultValue="sideBySide" className="w-full">
                <TabsList className="grid w-full max-w-[400px] grid-cols-3">
                  <TabsTrigger value="sideBySide">Side by Side</TabsTrigger>
                  <TabsTrigger value="overlay">Overlay</TabsTrigger>
                  <TabsTrigger value="heatmap">Heatmap</TabsTrigger>
                </TabsList>

                <TabsContent value="sideBySide" className="mt-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <div className="text-sm font-medium text-muted-foreground">
                        Before
                      </div>
                      <div className="aspect-video bg-gradient-to-br from-blue-100 to-blue-50 rounded-lg border border-border flex items-center justify-center">
                        <span className="text-muted-foreground text-sm">
                          Before Screenshot
                        </span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="text-sm font-medium text-muted-foreground">
                        After
                      </div>
                      <div className="aspect-video bg-gradient-to-br from-purple-100 to-purple-50 rounded-lg border border-border flex items-center justify-center">
                        <span className="text-muted-foreground text-sm">
                          After Screenshot
                        </span>
                      </div>
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="overlay" className="mt-4">
                  <div className="aspect-video bg-gradient-to-br from-gray-100 to-gray-50 rounded-lg border border-border flex items-center justify-center">
                    <span className="text-muted-foreground text-sm">
                      Overlay Comparison View
                    </span>
                  </div>
                </TabsContent>

                <TabsContent value="heatmap" className="mt-4">
                  <div className="aspect-video bg-gradient-to-br from-red-100 via-yellow-100 to-green-100 rounded-lg border border-border flex items-center justify-center">
                    <span className="text-muted-foreground text-sm">
                      Difference Heatmap
                    </span>
                  </div>
                </TabsContent>
              </Tabs>
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
};
