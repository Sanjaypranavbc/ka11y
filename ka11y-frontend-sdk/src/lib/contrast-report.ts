import { ContrastDetection, ContrastImageDetail, ContrastReport } from "@/types/audit";

export type ContrastFailureLevel = "AA" | "AAA";

export function getDetectionFailureLevels(detection: ContrastDetection): ContrastFailureLevel[] {
  const levels: ContrastFailureLevel[] = [];

  if (detection.AA_passes === false) levels.push("AA");
  if (detection.AAA_passes === false) levels.push("AAA");

  if (levels.length === 0 && detection.wcag_violations.some((violation) => /\bAAA\b/i.test(violation))) {
    levels.push("AAA");
  }

  if (levels.length === 0 && detection.wcag_violations.length > 0) {
    levels.push("AA");
  }

  return [...new Set(levels)];
}

export function isFailingDetection(detection: ContrastDetection): boolean {
  return getDetectionFailureLevels(detection).length > 0;
}

export function hasImageViolations(image: ContrastImageDetail): boolean {
  return image.detections.some(isFailingDetection);
}

export function getFailingDetections(image: ContrastImageDetail): ContrastDetection[] {
  return image.detections.filter(isFailingDetection);
}

export function getPassingDetections(image: ContrastImageDetail): ContrastDetection[] {
  return image.detections.filter((detection) => !isFailingDetection(detection));
}

export function getImageViolationCount(image: ContrastImageDetail): number {
  return image.detections.reduce(
    (count, detection) => count + getDetectionFailureLevels(detection).length,
    0,
  );
}

export function summariseContrastReport(report: ContrastReport) {
  const totalRegions = report.images.reduce(
    (count, image) => count + image.detections.length,
    0,
  );
  let totalViolations = 0;
  let imagesWithViolations = 0;
  let passingRegions = 0;

  for (const image of report.images) {
    const failingDetections = getFailingDetections(image);
    totalViolations += failingDetections.reduce(
      (count, detection) => count + getDetectionFailureLevels(detection).length,
      0,
    );
    passingRegions += image.detections.length - failingDetections.length;

    if (failingDetections.length > 0) {
      imagesWithViolations += 1;
    }
  }

  const passRatePct = totalRegions
    ? Number(((passingRegions / totalRegions) * 100).toFixed(1))
    : 0;

  return {
    total_regions_analysed: totalRegions || report.summary.total_regions_analysed || 0,
    total_violations: totalViolations,
    images_with_violations: imagesWithViolations,
    pass_rate_pct: passRatePct,
  };
}
