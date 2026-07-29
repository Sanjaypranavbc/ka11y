"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ImageOff,
  Images,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  ContrastImageDetail,
  ContrastReport,
  ImageClassification,
} from "@/lib/auditImages";

const CLASSIFICATION_LABEL: Record<ImageClassification, string> = {
  button: "Buttons",
  icon: "Icons",
  logo: "Logos",
  image: "Images",
  chart: "Charts",
  informative: "Informative",
  decorative: "Decorative",
  other: "Other",
};

const CLASSIFICATION_ORDER: ImageClassification[] = [
  "button",
  "icon",
  "logo",
  "image",
  "chart",
  "informative",
  "decorative",
  "other",
];

function hasViolations(img: ContrastImageDetail): boolean {
  return (
    img.contrast_violations_count > 0 ||
    img.detections.some((d) => d.wcag_violations.length > 0)
  );
}

function groupByClassification(
  images: ContrastImageDetail[],
): Map<ImageClassification, ContrastImageDetail[]> {
  const map = new Map<ImageClassification, ContrastImageDetail[]>();
  for (const img of images) {
    const key = img.classification ?? "other";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(img);
  }
  return map;
}

export function ImageVisualisationTab({
  report,
}: {
  report: ContrastReport | null | undefined;
}) {
  const [search, setSearch] = useState("");

  if (!report || report.images.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-[12px] border border-gray-10 bg-white p-10 text-center">
        <Images className="h-10 w-10 text-gray-40" aria-hidden="true" />
        <div>
          <h2 className="text-[15px] font-semibold text-brand-gray">No image data</h2>
          <p className="mt-1 max-w-xs text-[13px] text-gray-60">
            This audit did not capture any images, or OCR / contrast analysis was
            not enabled for the crawl.
          </p>
        </div>
      </div>
    );
  }

  const { summary, images } = report;

  const filtered = search
    ? images.filter((img) =>
        img.filename.toLowerCase().includes(search.toLowerCase()),
      )
    : images;

  const failed = filtered.filter(hasViolations);
  const passed = filtered.filter((img) => !hasViolations(img));
  const failedByClass = groupByClassification(failed);
  const passedByClass = groupByClassification(passed);

  return (
    <div className="space-y-6">
      {/* Summary tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryTile label="Regions Analysed" value={summary.total_regions_analysed} />
        <SummaryTile
          label="Contrast Violations"
          value={summary.total_violations}
          tone={summary.total_violations > 0 ? "danger" : "ok"}
        />
        <SummaryTile
          label="Images Affected"
          value={summary.images_with_violations}
          tone={summary.images_with_violations > 0 ? "warn" : "ok"}
        />
        <SummaryTile
          label="Pass Rate"
          value={`${summary.pass_rate_pct}%`}
          tone={
            summary.pass_rate_pct >= 90
              ? "ok"
              : summary.pass_rate_pct >= 60
                ? "warn"
                : "danger"
          }
        />
      </div>

      {/* Search */}
      <div className="relative w-full sm:w-72">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-40"
          aria-hidden="true"
        />
        <input
          type="text"
          placeholder="Filter by filename…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Filter images by filename"
          className="h-9 w-full rounded-[8px] border border-gray-10 bg-white pl-9 pr-3 text-[13px] text-brand-gray outline-none focus:border-brand-teal"
        />
      </div>

      {/* Failed */}
      <section aria-labelledby="iv-failed">
        <div className="mb-3 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-red-500" aria-hidden="true" />
          <h2 id="iv-failed" className="text-[14px] font-semibold text-brand-gray">
            Failed
          </h2>
          <span className="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-600">
            {failed.length}
          </span>
        </div>
        {failed.length === 0 ? (
          <p className="pl-1 text-[13px] text-gray-60">
            {search
              ? "No failed images match your search."
              : "No contrast violations found."}
          </p>
        ) : (
          CLASSIFICATION_ORDER.filter((c) => failedByClass.has(c)).map((c) => (
            <ClassGroup
              key={c}
              label={CLASSIFICATION_LABEL[c]}
              images={failedByClass.get(c)!}
              variant="failed"
            />
          ))
        )}
      </section>

      {/* Passed */}
      {passed.length > 0 && (
        <section aria-labelledby="iv-passed">
          <div className="mb-3 flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-600" aria-hidden="true" />
            <h2 id="iv-passed" className="text-[14px] font-semibold text-brand-gray">
              Passed
            </h2>
            <span className="rounded-full bg-green-50 px-2 py-0.5 text-[11px] font-medium text-green-700">
              {passed.length}
            </span>
          </div>
          {CLASSIFICATION_ORDER.filter((c) => passedByClass.has(c)).map((c) => (
            <ClassGroup
              key={c}
              label={CLASSIFICATION_LABEL[c]}
              images={passedByClass.get(c)!}
              variant="passed"
            />
          ))}
        </section>
      )}
    </div>
  );
}

function SummaryTile({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "ok" | "warn" | "danger";
}) {
  const toneCls = {
    neutral: "text-brand-gray",
    ok: "text-green-600",
    warn: "text-amber-500",
    danger: "text-red-500",
  }[tone];
  return (
    <div className="rounded-[12px] border border-gray-10 bg-white p-4">
      <p className="text-[12px] text-gray-60">{label}</p>
      <p className={cn("mt-1 text-[22px] font-semibold", toneCls)}>{value}</p>
    </div>
  );
}

function ClassGroup({
  label,
  images,
  variant,
}: {
  label: string;
  images: ContrastImageDetail[];
  variant: "failed" | "passed";
}) {
  return (
    <div className="mb-5">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[13px] font-medium text-brand-gray">{label}</span>
        <span className="text-[11px] text-gray-60">({images.length})</span>
      </div>
      {variant === "failed" ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {images.map((img) => (
            <FailedCard key={img.path} image={img} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
          {images.map((img) => (
            <PassedCard key={img.path} image={img} />
          ))}
        </div>
      )}
    </div>
  );
}

function FailedCard({ image }: { image: ContrastImageDetail }) {
  const [errored, setErrored] = useState(false);
  const failing = image.detections.filter((d) => d.wcag_violations.length > 0);

  return (
    <article className="flex flex-col overflow-hidden rounded-[12px] border border-red-200 bg-white shadow-sm">
      <div className="relative bg-gray-10">
        {errored ? (
          <ImgFallback filename={image.filename} />
        ) : (
          <img
            src={image.image_url}
            alt={`Image with contrast violations: ${image.filename}`}
            className="h-48 w-full object-contain"
            loading="lazy"
            onError={() => setErrored(true)}
          />
        )}
        <span className="absolute right-2 top-2 rounded bg-red-500 px-2 py-0.5 text-[10px] font-medium text-white shadow">
          {image.contrast_violations_count} violation
          {image.contrast_violations_count !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="flex-1 space-y-1.5 p-3">
        <p className="truncate text-[12px] font-medium text-brand-gray" title={image.filename}>
          {image.filename}
        </p>
        {failing.slice(0, 3).map((det, i) => (
          <div key={i} className="rounded-[6px] bg-red-50 px-2 py-1 text-[11px] text-red-700">
            <span className="truncate">{det.text || "(region)"}</span>
            {det.ratio != null && (
              <span className="ml-1 font-mono">· {det.ratio.toFixed(2)}:1</span>
            )}
          </div>
        ))}
        {failing.length > 3 && (
          <p className="text-[11px] text-gray-60">+{failing.length - 3} more region(s)</p>
        )}
      </div>
    </article>
  );
}

function PassedCard({ image }: { image: ContrastImageDetail }) {
  const [errored, setErrored] = useState(false);
  return (
    <article className="overflow-hidden rounded-[10px] border border-green-200 bg-white shadow-sm">
      <div className="relative bg-gray-10">
        {errored ? (
          <ImgFallback filename={image.filename} compact />
        ) : (
          <img
            src={image.image_url}
            alt={image.filename}
            className="h-24 w-full object-cover"
            loading="lazy"
            onError={() => setErrored(true)}
          />
        )}
        <CheckCircle2
          className="absolute right-1.5 top-1.5 h-4 w-4 text-green-600 drop-shadow"
          aria-hidden="true"
        />
      </div>
      <div className="p-2">
        <p className="truncate text-[11px] font-medium text-brand-gray" title={image.filename}>
          {image.filename}
        </p>
      </div>
    </article>
  );
}

function ImgFallback({ filename, compact }: { filename: string; compact?: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-1 bg-gray-10 text-gray-40",
        compact ? "h-24" : "h-48",
      )}
    >
      <ImageOff className="h-5 w-5" aria-hidden="true" />
      <span className="max-w-[90%] truncate px-2 text-[10px]">{filename}</span>
    </div>
  );
}
