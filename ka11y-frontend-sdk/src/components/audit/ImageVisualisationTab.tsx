import { useState } from "react";
import {
  ContrastImageDetail,
  ContrastReport,
  ImageAuditImageDetail,
  ImageAuditReport,
  ImageClassification,
} from "@/types/audit";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  DetectionRow,
  ImageErrorPlaceholder,
  SummaryTile,
} from "./ContrastReportSection";
import {
  CheckCircle2,
  AlertTriangle,
  Search,
  Images,
  MousePointerClick,
  Sparkles,
  ImageIcon,
  BadgeCheck,
  BarChart2,
  Tag,
  HelpCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getFailingDetections,
  getImageViolationCount,
  getPassingDetections,
  hasImageViolations,
  summariseContrastReport,
} from "@/lib/contrast-report";

// ── Classification metadata ───────────────────────────────────────────────────

const CLASSIFICATION_META: Record<
  ImageClassification,
  { label: string; Icon: React.ElementType; color: string }
> = {
  button:      { label: "Buttons",      Icon: MousePointerClick, color: "text-blue-500" },
  icon:        { label: "Icons",        Icon: Sparkles,          color: "text-purple-500" },
  logo:        { label: "Logos",        Icon: BadgeCheck,        color: "text-amber-500" },
  image:       { label: "Images",       Icon: ImageIcon,         color: "text-green-500" },
  chart:       { label: "Charts",       Icon: BarChart2,         color: "text-cyan-500" },
  informative: { label: "Informative",  Icon: Tag,               color: "text-teal-500" },
  decorative:  { label: "Decorative",   Icon: Images,            color: "text-slate-500" },
  other:       { label: "Other",        Icon: HelpCircle,        color: "text-muted-foreground" },
};

const CLASSIFICATION_ORDER: ImageClassification[] = [
  "button", "icon", "logo", "image", "chart", "informative", "decorative", "other",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function groupByClassification(
  images: Array<{ classification?: ImageClassification }>,
): Map<ImageClassification, typeof images> {
  const map = new Map<ImageClassification, typeof images>();
  for (const img of images) {
    const key = img.classification ?? "other";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(img);
  }
  return map;
}

// ── Main tab ──────────────────────────────────────────────────────────────────

interface ImageVisualisationTabProps {
  contrastReport: ContrastReport | null | undefined;
  imageAuditReport: ImageAuditReport | null | undefined;
}

export function ImageVisualisationTab({
  contrastReport,
  imageAuditReport,
}: ImageVisualisationTabProps) {
  const [search, setSearch] = useState("");
  const hasContrastImages = Boolean(contrastReport && contrastReport.images.length > 0);
  const hasAuditImages = Boolean(imageAuditReport && imageAuditReport.images.length > 0);

  if (!hasContrastImages && !hasAuditImages) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-center p-8 grid-bg min-h-full">
        <Images className="h-12 w-12 text-muted-foreground/40" aria-hidden="true" />
        <div>
          <h2 className="text-sm font-semibold text-foreground">No image data</h2>
          <p className="text-xs text-muted-foreground mt-1 max-w-xs">
            Run an audit with image audit or OCR enabled to visualise audited images.
          </p>
        </div>
      </div>
    );
  }

  if (!hasContrastImages && hasAuditImages && imageAuditReport) {
    return <ImageAuditFallbackView imageAuditReport={imageAuditReport} search={search} setSearch={setSearch} />;
  }

  const summary = summariseContrastReport(contrastReport);
  const { images } = contrastReport;

  const filtered = search
    ? images.filter((img) => img.filename.toLowerCase().includes(search.toLowerCase()))
    : images;

  const failedFiltered = filtered.filter(hasImageViolations);
  const passedFiltered = filtered.filter((img) => !hasImageViolations(img));
  const failedByClass = groupByClassification(failedFiltered);
  const passedByClass = groupByClassification(passedFiltered);

  return (
    <div className="p-3 sm:p-5 space-y-6 grid-bg min-h-full animate-fade-up">
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
      <div className="relative w-full sm:w-64">
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
      {failedFiltered.length > 0 && (
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

          {CLASSIFICATION_ORDER.filter((cls) => failedByClass.has(cls)).map((cls) => (
            <ClassificationGroup
              key={cls}
              classification={cls}
              images={failedByClass.get(cls)!}
              variant="failed"
            />
          ))}
        </section>
      )}

      {failedFiltered.length === 0 && (
        <p className="text-xs text-muted-foreground py-4 pl-1">
          {search ? "No failed images match your search." : "No contrast violations found — great work!"}
        </p>
      )}

      {/* ── Passed section ──────────────────────────────────────────────────── */}
      {passedFiltered.length > 0 && (
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

          {CLASSIFICATION_ORDER.filter((cls) => passedByClass.has(cls)).map((cls) => (
            <ClassificationGroup
              key={cls}
              classification={cls}
              images={passedByClass.get(cls)!}
              variant="passed"
            />
          ))}
        </section>
      )}
    </div>
  );
}

function ImageAuditFallbackView({
  imageAuditReport,
  search,
  setSearch,
}: {
  imageAuditReport: ImageAuditReport;
  search: string;
  setSearch: (value: string) => void;
}) {
  const { summary, images } = imageAuditReport;
  const filtered = search
    ? images.filter((img) => {
        const haystack = `${img.filename} ${img.alt_text || ""} ${img.src || ""}`.toLowerCase();
        return haystack.includes(search.toLowerCase());
      })
    : images;

  const failedFiltered = filtered.filter((img) => img.overall_status !== "PASSED");
  const passedFiltered = filtered.filter((img) => img.overall_status === "PASSED");
  const failedByClass = groupByClassification(failedFiltered);
  const passedByClass = groupByClassification(passedFiltered);

  return (
    <div className="p-3 sm:p-5 space-y-6 grid-bg min-h-full animate-fade-up">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryTile label="Audited Images" value={summary.total_images} />
        <SummaryTile
          label="Failed Images"
          value={summary.failed}
          variant={summary.failed > 0 ? "danger" : "ok"}
        />
        <SummaryTile
          label="Passed Images"
          value={summary.passed}
          variant={summary.passed > 0 ? "ok" : "default"}
        />
        <SummaryTile
          label="Images With OCR Text"
          value={summary.with_ocr_text}
          variant={summary.with_ocr_text > 0 ? "warn" : "default"}
        />
      </div>

      <div className="relative w-full sm:w-64">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" aria-hidden="true" />
        <Input
          placeholder="Filter by filename or alt text…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-8 h-8 text-xs"
          aria-label="Filter audited images"
        />
      </div>

      <section aria-labelledby="failed-images-heading">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden="true" />
          <h2 id="failed-images-heading" className="text-sm font-semibold text-foreground">
            Failed Image Audits
          </h2>
          <Badge variant="destructive" className="text-[10px]">
            {failedFiltered.length}
          </Badge>
        </div>

        {failedFiltered.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 pl-1">
            {search ? "No failed image audits match your search." : "No failed image audits found."}
          </p>
        ) : (
          CLASSIFICATION_ORDER.filter((cls) => failedByClass.has(cls)).map((cls) => (
            <div key={cls} className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                {(() => {
                  const meta = CLASSIFICATION_META[cls] ?? CLASSIFICATION_META.other;
                  const Icon = meta.Icon;
                  return <Icon className={cn("h-3.5 w-3.5", meta.color)} aria-hidden="true" />;
                })()}
                <span className="text-xs font-medium text-foreground">
                  {(CLASSIFICATION_META[cls] ?? CLASSIFICATION_META.other).label}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  ({failedByClass.get(cls)!.length})
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {failedByClass.get(cls)!.map((img) => (
                  <FailedAuditImageCard key={img.path} image={img as ImageAuditImageDetail} />
                ))}
              </div>
            </div>
          ))
        )}
      </section>

      {passedFiltered.length > 0 && (
        <section aria-labelledby="passed-images-heading">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
            <h2 id="passed-images-heading" className="text-sm font-semibold text-foreground">
              Passed Image Audits
            </h2>
            <Badge className="text-[10px] bg-success/20 text-success border-success/30" variant="outline">
              {passedFiltered.length}
            </Badge>
          </div>

          {CLASSIFICATION_ORDER.filter((cls) => passedByClass.has(cls)).map((cls) => (
            <div key={cls} className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                {(() => {
                  const meta = CLASSIFICATION_META[cls] ?? CLASSIFICATION_META.other;
                  const Icon = meta.Icon;
                  return <Icon className={cn("h-3.5 w-3.5", meta.color)} aria-hidden="true" />;
                })()}
                <span className="text-xs font-medium text-foreground">
                  {(CLASSIFICATION_META[cls] ?? CLASSIFICATION_META.other).label}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  ({passedByClass.get(cls)!.length})
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-3">
                {passedByClass.get(cls)!.map((img) => (
                  <PassedAuditImageCard key={img.path} image={img as ImageAuditImageDetail} />
                ))}
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

// ── Classification group ──────────────────────────────────────────────────────

function ClassificationGroup({
  classification,
  images,
  variant,
}: {
  classification: ImageClassification;
  images: ContrastImageDetail[];
  variant: "failed" | "passed";
}) {
  const meta = CLASSIFICATION_META[classification] ?? CLASSIFICATION_META.other;
  const { label, Icon, color } = meta;

  return (
    <div className="mb-6">
      {/* Group header */}
      <div className="flex items-center gap-2 mb-3">
        <Icon className={cn("h-3.5 w-3.5", color)} aria-hidden="true" />
        <span className="text-xs font-medium text-foreground">{label}</span>
        <span className="text-[10px] text-muted-foreground">({images.length})</span>
      </div>

      {variant === "failed" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {images.map((img) => (
            <FailedImageCard key={img.path} image={img} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-3">
          {images.map((img) => (
            <PassedImageCard key={img.path} image={img} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Failed image card — full detail ──────────────────────────────────────────

function FailedImageCard({ image }: { image: ContrastImageDetail }) {
  const [imgError, setImgError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const failingDetections = getFailingDetections(image);
  const violationCount = getImageViolationCount(image);
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
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-3 py-2">
          <p className="text-white text-[10px] font-medium truncate">{image.filename}</p>
        </div>
        <Badge className="absolute top-2 right-2 text-[9px] bg-destructive shadow">
          {violationCount} violation{violationCount !== 1 ? "s" : ""}
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
  const passingCount = getPassingDetections(image).length;

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

function FailedAuditImageCard({ image }: { image: ImageAuditImageDetail }) {
  const [imgError, setImgError] = useState(false);
  const reasons = [
    image.wcag_1_1_1_status === "FAILED" && { key: "1.1.1", text: image.wcag_1_1_1_reason },
    image.wcag_4_1_2_status === "FAILED" && { key: "4.1.2", text: image.wcag_4_1_2_reason },
    image.wcag_1_4_5_status === "FAILED" && { key: "1.4.5", text: image.wcag_1_4_5_reason },
    (image.wcag_1_4_11_status === "FAILED" || image.wcag_1_4_11_status === "INCOMPLETE") && {
      key: "1.4.11",
      text: image.wcag_1_4_11_reason,
    },
  ].filter(Boolean) as Array<{ key: string; text: string }>;

  return (
    <article
      className="rounded-xl border border-destructive/40 overflow-hidden bg-card shadow-sm flex flex-col"
      aria-label={`Failed image audit: ${image.filename}`}
    >
      <div className="relative bg-muted/40 shrink-0">
        {imgError ? (
          <ImageErrorPlaceholder filename={image.filename} height="h-52" />
        ) : (
          <img
            src={image.image_url}
            alt={`Audited image: ${image.filename}`}
            className="w-full h-52 object-contain"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        )}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-3 py-2">
          <p className="text-white text-[10px] font-medium truncate">{image.filename}</p>
        </div>
      </div>

      <div className="p-3 space-y-2 flex-1">
        <div className="flex flex-wrap gap-1">
          <AuditStatusBadge label="1.1.1" status={image.wcag_1_1_1_status} />
          {image.wcag_4_1_2_status !== "N/A" && (
            <AuditStatusBadge label="4.1.2" status={image.wcag_4_1_2_status} />
          )}
          {image.wcag_1_4_5_status !== "N/A" && (
            <AuditStatusBadge label="1.4.5" status={image.wcag_1_4_5_status} />
          )}
          {image.wcag_1_4_11_status !== "N/A" && (
            <AuditStatusBadge label="1.4.11" status={image.wcag_1_4_11_status} />
          )}
        </div>

        <div className="space-y-1 text-[10px] text-muted-foreground">
          {image.alt_text ? <p><span className="font-medium text-foreground">Alt:</span> {image.alt_text}</p> : <p><span className="font-medium text-foreground">Alt:</span> Missing or empty</p>}
          {image.detected_text && (
            <p><span className="font-medium text-foreground">OCR:</span> {image.detected_text}</p>
          )}
          {image.contrast_violations_count > 0 && (
            <p><span className="font-medium text-foreground">Contrast flags:</span> {image.contrast_violations_count}</p>
          )}
        </div>

        <div className="space-y-1.5">
          {reasons.slice(0, 3).map((reason) => (
            <div key={reason.key} className="rounded-md border border-border/60 bg-muted/30 p-2">
              <p className="text-[10px] font-medium text-foreground">WCAG {reason.key}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{reason.text}</p>
            </div>
          ))}
        </div>
      </div>
    </article>
  );
}

function PassedAuditImageCard({ image }: { image: ImageAuditImageDetail }) {
  const [imgError, setImgError] = useState(false);

  return (
    <article
      className="rounded-lg border border-success/30 overflow-hidden bg-card shadow-sm"
      aria-label={`Passed image audit: ${image.filename}`}
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
          {image.alt_text ? `Alt: ${image.alt_text}` : "Audited image passed"}
        </p>
      </div>
    </article>
  );
}

function AuditStatusBadge({ label, status }: { label: string; status: string }) {
  const isPass = status === "PASSED";
  const isReview = status === "INCOMPLETE";

  return (
    <Badge
      variant="outline"
      className={cn(
        "text-[9px]",
        isPass && "border-success/40 text-success bg-success/10",
        !isPass && !isReview && "border-destructive/40 text-destructive bg-destructive/10",
        isReview && "border-amber-400/40 text-amber-600 bg-amber-500/10",
      )}
    >
      {label} {status}
    </Badge>
  );
}
