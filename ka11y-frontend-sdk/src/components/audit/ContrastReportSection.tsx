import { useState } from "react";
import { ContrastImageDetail, ContrastReport } from "@/types/audit";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronDown, AlertTriangle, CheckCircle2, Eye } from "lucide-react";
import { cn } from "@/lib/utils";

interface ContrastReportSectionProps {
  report: ContrastReport;
}

export function ContrastReportSection({ report }: ContrastReportSectionProps) {
  const { summary, images } = report;
  const [passingOpen, setPassingOpen] = useState(false);

  const violating = images.filter((img) => img.contrast_violations_count > 0);
  const passing   = images.filter((img) => img.contrast_violations_count === 0);

  return (
    <Card className="animate-fade-up">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Eye className="h-4 w-4" aria-hidden="true" />
          Contrast Analysis — WCAG 1.4.3
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary tiles */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <SummaryTile label="Regions Analysed" value={summary.total_regions_analysed} />
          <SummaryTile label="Contrast Violations" value={summary.total_violations}
            variant={summary.total_violations > 0 ? "danger" : "ok"} />
          <SummaryTile label="Images Affected" value={summary.images_with_violations}
            variant={summary.images_with_violations > 0 ? "warn" : "ok"} />
          <SummaryTile label="Pass Rate" value={`${summary.pass_rate_pct}%`}
            variant={summary.pass_rate_pct >= 90 ? "ok" : summary.pass_rate_pct >= 60 ? "warn" : "danger"} />
        </div>

        {/* Violating images */}
        {violating.length > 0 && (
          <section aria-label="Images with contrast violations">
            <h4 className="text-[10px] font-semibold tracking-widest uppercase text-destructive mb-3">
              Images with Violations
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {violating.map((img) => (
                <ContrastImageCard key={img.path} image={img} />
              ))}
            </div>
          </section>
        )}

        {/* Passing images — collapsed */}
        {passing.length > 0 && (
          <Collapsible open={passingOpen} onOpenChange={setPassingOpen}>
            <CollapsibleTrigger className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors">
              <ChevronDown className={cn("h-3 w-3 transition-transform", passingOpen && "rotate-180")} aria-hidden="true" />
              <CheckCircle2 className="h-3 w-3 text-success" aria-hidden="true" />
              {passing.length} image{passing.length !== 1 ? "s" : ""} passed contrast check
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 mt-3">
                {passing.map((img) => (
                  <PassingThumb key={img.path} image={img} />
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}

        {images.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-4">
            No images were analysed for contrast.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ── Shared sub-components ─────────────────────────────────────────────────────

export function SummaryTile({
  label,
  value,
  variant = "neutral",
}: {
  label: string;
  value: string | number;
  variant?: "neutral" | "danger" | "warn" | "ok";
}) {
  const bg      = { neutral: "bg-muted/50", danger: "bg-destructive/10", warn: "bg-moderate/10", ok: "bg-success/10" }[variant];
  const textCls = { neutral: "text-foreground", danger: "text-destructive", warn: "text-moderate", ok: "text-success" }[variant];
  return (
    <div className={cn("rounded-lg p-3 space-y-1", bg)}>
      <p className="text-[10px] text-muted-foreground leading-tight">{label}</p>
      <p className={cn("text-xl font-bold tabular-nums", textCls)}>{value}</p>
    </div>
  );
}

export function ContrastImageCard({ image }: { image: ContrastImageDetail }) {
  const [imgError, setImgError] = useState(false);
  const failingDetections = image.detections.filter((d) => d.wcag_violations.length > 0);

  return (
    <article className="rounded-lg border border-destructive/30 overflow-hidden bg-card"
      aria-label={`Contrast violations in ${image.filename}`}>
      <div className="relative bg-muted/50">
        {imgError ? (
          <ImageErrorPlaceholder filename={image.filename} height="h-44" />
        ) : (
          <img src={image.image_url} alt={`Audited: ${image.filename}`}
            className="w-full h-44 object-contain" loading="lazy"
            onError={() => setImgError(true)} />
        )}
        <Badge className="absolute top-1.5 right-1.5 text-[9px] bg-destructive/90">
          {image.contrast_violations_count} violation{image.contrast_violations_count !== 1 ? "s" : ""}
        </Badge>
      </div>
      <div className="p-3 space-y-2">
        <p className="text-xs font-medium truncate" title={image.filename}>{image.filename}</p>
        <div className="space-y-1.5" role="list" aria-label="Contrast violations">
          {failingDetections.slice(0, 4).map((det, i) => (
            <DetectionRow key={i} detection={det} />
          ))}
          {failingDetections.length > 4 && (
            <p className="text-[10px] text-muted-foreground italic">
              +{failingDetections.length - 4} more…
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

export function DetectionRow({ detection }: { detection: ContrastImageDetail["detections"][number] }) {
  return (
    <div role="listitem" className="rounded bg-destructive/5 border border-destructive/20 px-2 py-1.5 space-y-1">
      <p className="text-[10px] font-medium text-foreground break-words leading-snug">
        &ldquo;{detection.text}&rdquo;
      </p>
      <div className="flex items-center gap-1.5 flex-wrap">
        {detection.ratio !== null && (
          <span className="text-[10px] font-mono text-destructive">{detection.ratio.toFixed(2)}:1</span>
        )}
        {detection.wcag_violations.map((v, i) => (
          <Badge key={i} variant="destructive" className="text-[9px] px-1 py-0 h-4">{v}</Badge>
        ))}
      </div>
    </div>
  );
}

export function PassingThumb({ image }: { image: ContrastImageDetail }) {
  const [imgError, setImgError] = useState(false);
  return (
    <div className="rounded border border-border overflow-hidden" title={image.filename}>
      {imgError ? (
        <div className="h-20 flex items-center justify-center bg-muted/50">
          <AlertTriangle className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        </div>
      ) : (
        <img src={image.image_url} alt={image.filename}
          className="w-full h-20 object-cover" loading="lazy"
          onError={() => setImgError(true)} />
      )}
      <p className="text-[9px] text-muted-foreground px-1 py-0.5 truncate bg-muted/30">{image.filename}</p>
    </div>
  );
}

export function ImageErrorPlaceholder({ filename, height = "h-44" }: { filename: string; height?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground", height)}>
      <AlertTriangle className="h-5 w-5" aria-hidden="true" />
      <span>Image unavailable</span>
      <span className="font-mono text-[10px] px-2 text-center break-all max-w-[180px]">{filename}</span>
    </div>
  );
}