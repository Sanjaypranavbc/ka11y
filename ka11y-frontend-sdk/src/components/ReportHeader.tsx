import { Download, Share2, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

interface ReportHeaderProps {
  scanDate: string;
  scanUrl: string;
  includePdf: boolean;
  onPdfToggle: (checked: boolean) => void;
  onDownload: () => void;
  onShare: () => void;
}

export const ReportHeader = ({
  scanDate,
  scanUrl,
  includePdf,
  onPdfToggle,
  onDownload,
  onShare,
}: ReportHeaderProps) => {
  return (
    <header className="sticky top-0 z-50 bg-card border-b border-border shadow-sm backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex flex-col gap-4">
          <div className="flex-1">
            <h1 className="text-3xl font-bold text-foreground mb-2">
              Your Accessibility & Visual Report Is Ready
            </h1>
            <p className="text-muted-foreground max-w-2xl">
              Here's the complete analysis of your website, including issues found, helpful suggestions, and recommended fixes.
            </p>
          </div>

          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <span className="font-medium text-foreground">URL:</span>
                <span className="truncate max-w-md">{scanUrl}</span>
              </div>
              <span className="hidden sm:inline">•</span>
              <div className="flex items-center gap-2">
                <span className="font-medium text-foreground">Scanned:</span>
                <span>{scanDate}</span>
              </div>
              <span className="hidden sm:inline">•</span>
              <div className="flex items-center gap-2">
                <span className="font-medium text-foreground">Standard:</span>
                <span>WCAG 2.1 Level AA</span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted border border-border">
                <Checkbox
                  id="include-pdf"
                  checked={includePdf}
                  onCheckedChange={onPdfToggle}
                />
                <label
                  htmlFor="include-pdf"
                  className="text-sm font-medium cursor-pointer flex items-center gap-2"
                >
                  <FileText className="h-4 w-4" />
                  Include PDF Version
                </label>
              </div>

              <Button onClick={onShare} variant="outline">
                <Share2 className="h-4 w-4 mr-2" />
                Share Link
              </Button>

              <Button onClick={onDownload}>
                <Download className="h-4 w-4 mr-2" />
                Download Report
              </Button>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
