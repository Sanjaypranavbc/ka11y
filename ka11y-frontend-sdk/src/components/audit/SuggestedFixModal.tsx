import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Copy, ExternalLink } from "lucide-react";
import { toast } from "sonner";

interface SuggestedFixModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  wcagSc: string | null;
  criterionName: string | null;
  suggestedFix: string | null;
  elementHtml: string;
  helpUrl?: string;
}

export function SuggestedFixModal({
  open, onOpenChange, wcagSc, criterionName, suggestedFix, elementHtml, helpUrl,
}: SuggestedFixModalProps) {
  const copyHtml = () => {
    navigator.clipboard.writeText(elementHtml);
    toast.success("HTML copied to clipboard");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 flex-wrap">
            {wcagSc && <Badge variant="outline" className="font-mono shrink-0">{wcagSc}</Badge>}
            <span className="break-words">{criterionName}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          {suggestedFix && (
            <div>
              <h4 className="text-sm font-medium text-foreground mb-2">Suggested Fix</h4>
              <blockquote className="border-l-4 border-primary pl-4 text-sm text-muted-foreground italic break-words leading-relaxed">
                {suggestedFix}
              </blockquote>
            </div>
          )}

          {elementHtml && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-medium text-foreground">Element HTML</h4>
                <Button variant="ghost" size="sm" onClick={copyHtml}>
                  <Copy className="h-3 w-3 mr-1" /> Copy
                </Button>
              </div>
              <div className="bg-muted rounded-md p-3 overflow-x-auto">
                <pre className="text-xs whitespace-pre-wrap break-all leading-relaxed">
                  <code>{elementHtml}</code>
                </pre>
              </div>
            </div>
          )}

          {helpUrl && (
            <Button variant="outline" size="sm" asChild>
              <a href={helpUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-3 w-3 mr-1.5" /> Learn more
              </a>
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
