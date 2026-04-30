/**
 * @fileoverview Adapts WCAG 2.5.4 violations into standardized flat report items.
 */
export function adaptToReportFormat(auditResult) {
  if (!auditResult || !Array.isArray(auditResult.manualReviewItems)) return [];

  return auditResult.manualReviewItems.map((item, index) => ({
    id: `wcag-2.5.4-${index}`,
    rule: "2.5.4 Motion Actuation",
    level: "A",
    severity: item.severity,
    url: item.pageUrl,
    lang: item.pageLang,
    element: "N/A (page-level)",
    selector: "N/A",
    message: item.message,
    helpUrl: item.helpUrl,
    manualReviewRequired: true,
    details: {
      requirement: item.requirement,
      motionLibraries: item.motionLibrariesDetected,
      motionEvidence: item.motionEvidence,
      disableControlFound: item.disableControlFound,
      disableControlEvidence: item.disableControlEvidence,
      likelyEssential: item.likelyEssential,
      essentialReason: item.essentialReason,
      confidence: item.confidence,
      layer: item.layer
    }
  }));
}

export function generateManualChecklistHTML(auditResult) {
  const url = auditResult.pageUrl || 'N/A';
  const conf = auditResult.summary?.confidence || 'none';
  const libs = auditResult.motionLibrariesDetected?.join(', ') || 'None';

  return `
<div class="wcag-254-checklist">
  <h3>Manual Verification Checklist — WCAG 2.5.4 Motion Actuation</h3>
  <p>URL: ${url}</p>
  <p>Motion signals detected: ${conf} confidence</p>
  <p>Libraries: ${libs}</p>
  <ol>
    <li>
      <input type="checkbox">
      Open this page on a mobile device. Shake or tilt the device.
      Does any content change or action trigger?
    </li>
    <li>
      <input type="checkbox">
      If yes — is there a UI button/control that does the same thing?
    </li>
    <li>
      <input type="checkbox">
      Is there a settings option to disable motion-based interactions?
    </li>
    <li>
      <input type="checkbox">
      Does disabling OS-level motion settings (iOS: Settings > Accessibility > Motion)
      prevent the motion actuation from triggering?
    </li>
    <li>
      <input type="checkbox">
      If essential motion (e.g. step counter) — verify it is truly essential and
      cannot be meaningfully replaced.
    </li>
  </ol>
</div>
  `.trim();
}