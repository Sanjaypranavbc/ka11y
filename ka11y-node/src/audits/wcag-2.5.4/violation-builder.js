/**
 * @fileoverview Builds standardised violation objects for WCAG 2.5.4
 */

function buildMessage(requirement, disableControl, essentialClassification) {
  let msg = `Motion actuation detected. `;
  if (requirement === 'ui-alternative') {
    msg += `Requirement Failed: No UI alternative found to trigger the motion-based action. `;
  } else {
    msg += `Requirement Failed: No UI control found to disable the motion actuation. `;
  }

  if (essentialClassification.likelyEssential) {
    msg += `(Note: This motion appears to be essential: ${essentialClassification.reason}, so it may be exempt. Please verify manually). `;
  } else {
    msg += `This motion does not appear to be essential. `;
  }
  msg += `Manual verification required on a real device.`;
  return msg;
}

function buildViolation({ motionEvidence, disableControl, detectedLibraries, essentialClassification, requirement, pageUrl, pageLang, layer }) {
  return {
    ruleId: "wcag-2.5.4-motion-actuation",
    wcag: "2.5.4",
    wcagLevel: "A",
    wcagVersion: "2.1",
    impact: essentialClassification.likelyEssential ? "moderate" : "critical",
    requirement: requirement,
    layer: layer,
    pageUrl: pageUrl,
    pageLang: pageLang,
    motionLibrariesDetected: [...detectedLibraries.keys()],
    motionEvidence: motionEvidence.rawEvidence,
    disableControlFound: disableControl.hasDisableControl,
    disableControlEvidence: disableControl.evidence,
    likelyEssential: essentialClassification.likelyEssential,
    essentialReason: essentialClassification.reason,
    confidence: motionEvidence.confidence,
    severity: essentialClassification.likelyEssential
      ? "warning"
      : disableControl.hasDisableControl
        ? "warning"
        : "violation",
    message: buildMessage(requirement, disableControl, essentialClassification),
    helpUrl: "https://www.w3.org/WAI/WCAG21/Understanding/motion-actuation.html",
    manualReviewRequired: true,
    timestamp: new Date().toISOString()
  };
}

module.exports = { buildViolation };
