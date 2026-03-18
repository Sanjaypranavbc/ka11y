import { useState } from "react";
import { ContrastImageDetail, ContrastReport } from "@/types/audit";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  ContrastImageCard,
  DetectionRow,
  ImageErrorPlaceholder,
  PassingThumb,
  SummaryTile,
} from "./ContrastReportSection";
import { CheckCircle2, AlertTriangle, Search, Images } from "lucide-react";
import { cn } from "@/lib/utils";

interface ImageVisualisationTabProps {
  contrastReport: ContrastReport | null | undefined;
}

export function ImageVisualisationTab({ contrastReport }: ImageVisualisationTabProps) {
  const [search, setSearch] = useState("");

  // ── Empty state ──────────────────────────────────────────────────────────────
  if (!contrastReport || contrastReport.images.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-center p-8 grid-bg min-h-full">
        <Images className="h-12 w-12 text-muted-foreground/40" aria-hidden="true" />
        <div>
          <h2 className="text-sm font-semibold text-foreground">No image data</h2>
          <p className="text-xs text-muted-foreground mt-1 max-w-xs">
            Run an audit with OCR enabled to visualise contrast findings per image.
          </p>
        </div>
      </div>
    );
  }

  const { summary, images } = contrastReport;

  const filtered = search
    ? images.filter((img) => img.filename.toLowerCase().includes(search.toLowerCase()))
    : images;

  const failedFiltered = filtered.filter((img) => img.contrast_violations_count > 0);
  const passedFiltered = filtered.filter((img) => img.contrast_violations_count === 0);

  return (
    <div className="p-5 space-y-6 grid-bg min-h-full animate-fade-up">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryTile label="Regions Analysed"    value={summary.total_regions_analysed} />
        <SummaryTile label="Contrast Violations" value={summary.total_violations}
          variant={summary.total_violations > 0 ? "danger" : "ok"} />
        <SummaryTile label="Images Affected"     value={summary.images_with_violations}
          variant={summary.images_with_violations > 0 ? "warn" : "ok"} />
        <SummaryTile label="Pass Rate"           value={`${summary.pass_rate_pct}%`}
          variant={summary.pass_rate_pct >= 90 ? "ok" : summary.pass_rate_pct >= 60 ? "warn" : "danger"} />
      </div>

      {/* Search */}
      <div className="relative w-64">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" aria-hidden="true" />
        <Input
          placeholder="Filter by filename…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-8 h-8 text-xs"
          aria-label="Filter images by filename"
        />
      </div>

      {/* ── Failed section ──────────────────────────────────────────────────── */}
      <section aria-labelledby="failed-heading">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden="true" />
          <h2 id="failed-heading" className="text-sm font-semibold text-foreground">
            Failed
          </h2>
          <Badge variant="destructive" className="text-[10px]">
            {failedFiltered.length}
          </Badge>
        </div>

        {failedFiltered.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 pl-1">
            {search ? "No failed images match your search." : "No contrast violations found — great work!"}
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {failedFiltered.map((img) => (
              <FailedImageCard key={img.path} image={img} />
            ))}
          </div>
        )}
      </section>

      {/* ── Passed section ──────────────────────────────────────────────────── */}
      <section aria-labelledby="passed-heading">
        <div className="flex items-center gap-2 mb-4">
          <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
          <h2 id="passed-heading" className="text-sm font-semibold text-foreground">
            Passed
          </h2>
          <Badge className="text-[10px] bg-success/20 text-success border-success/30" variant="outline">
            {passedFiltered.length}
          </Badge>
        </div>

        {passedFiltered.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 pl-1">
            {search ? "No passing images match your search." : "No images passed contrast check."}
          </p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-3">
            {passedFiltered.map((img) => (
              <PassedImageCard key={img.path} image={img} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ── Failed image card — full detail ──────────────────────────────────────────

function FailedImageCard({ image }: { image: ContrastImageDetail }) {
  const [imgError, setImgError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const failingDetections = image.detections.filter((d) => d.wcag_violations.length > 0);
  const showCount = expanded ? failingDetections.length : 3;

  return (
    <article
      className="rounded-xl border border-destructive/40 overflow-hidden bg-card shadow-sm flex flex-col"
      aria-label={`Failed: ${image.filename}`}
    >
      {/* Image */}
      <div className="relative bg-muted/40 shrink-0">
        {imgError ? (
          <ImageErrorPlaceholder filename={image.filename} height="h-52" />
        ) : (
          <img
            src={image.image_url}
            alt={`Image with contrast violations: ${image.filename}`}
            className="w-full h-52 object-contain"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        )}
        {/* Overlay badge */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-3 py-2">
          <p className="text-white text-[10px] font-medium truncate">{image.filename}</p>
        </div>
        <Badge className="absolute top-2 right-2 text-[9px] bg-destructive shadow">
          {image.contrast_violations_count} violation{image.contrast_violations_count !== 1 ? "s" : ""}
        </Badge>
      </div>

      {/* Violations list */}
      <div className="p-3 space-y-1.5 flex-1">
        <p className="text-[10px] font-semibold text-destructive uppercase tracking-wider mb-2">
          Failing Regions
        </p>
        <div role="list" aria-label={`Violations in ${image.filename}`} className="space-y-1.5">
          {failingDetections.slice(0, showCount).map((det, i) => (
            <DetectionRow key={i} detection={det} />
          ))}
        </div>
        {failingDetections.length > 3 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-[10px] text-primary hover:underline mt-1"
          >
            {expanded
              ? "Show less"
              : `Show ${failingDetections.length - 3} more region${failingDetections.length - 3 !== 1 ? "s" : ""}…`}
          </button>
        )}
      </div>
    </article>
  );
}

// ── Passed image card — compact ───────────────────────────────────────────────

function PassedImageCard({ image }: { image: ContrastImageDetail }) {
  const [imgError, setImgError] = useState(false);
  const passingCount = image.detections.filter((d) => d.wcag_violations.length === 0).length;

  return (
    <article
      className="rounded-lg border border-success/30 overflow-hidden bg-card shadow-sm"
      aria-label={`Passed: ${image.filename}`}
    >
      <div className="relative bg-muted/40">
        {imgError ? (
          <div className={cn("h-28 flex items-center justify-center bg-muted/50")}>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </div>
        ) : (
          <img
            src={image.image_url}
            alt={image.filename}
            className="w-full h-28 object-cover"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        )}
        <CheckCircle2
          className="absolute top-1.5 right-1.5 h-4 w-4 text-success drop-shadow"
          aria-hidden="true"
        />
      </div>
      <div className="p-2 space-y-0.5">
        <p className="text-[10px] font-medium truncate" title={image.filename}>
          {image.filename}
        </p>
        <p className="text-[9px] text-muted-foreground">
          {passingCount} region{passingCount !== 1 ? "s" : ""} ✓
        </p>
      </div>
    </article>
  );
}