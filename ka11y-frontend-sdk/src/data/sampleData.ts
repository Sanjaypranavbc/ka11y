import { AuditResult, AuditViolation, AuditNeedsReview, AuditPass } from "@/types/audit";

const generateViolations = (): AuditViolation[] => {
  const violations: AuditViolation[] = [];

  // 1.1.1 Non-text Content - 24 violations
  for (let i = 0; i < 24; i++) {
    violations.push({
      rule_id: `image-alt-${i}`,
      wcag_sc: "1.1.1",
      criterion_name: "Non-text Content",
      level: "A",
      severity: i < 8 ? "critical" : i < 16 ? "high" : "medium",
      source: i < 10 ? "axe" : "python",
      reason: `Image element ${i < 12 ? "is missing alt attribute" : "has empty alt text but is not decorative"}`,
      element_html: `<img src="/images/banner-${i}.jpg" class="hero-img">`,
      suggested_fix: "Add a descriptive alt attribute to the image that conveys the same information as the image.",
      help_url: "https://dequeuniversity.com/rules/axe/4.6/image-alt",
    });
  }

  // 2.5.3 Label in Name - 25 violations
  for (let i = 0; i < 25; i++) {
    violations.push({
      rule_id: `label-in-name-${i}`,
      wcag_sc: "2.5.3",
      criterion_name: "Label in Name",
      level: "A",
      severity: i < 5 ? "high" : "medium",
      source: "python",
      reason: `Interactive element's accessible name "${["Submit", "Click here", "Read more", "Learn more", "Go"][i % 5]}" does not contain its visible text`,
      element_html: `<button aria-label="action-${i}" class="btn">Read More</button>`,
      suggested_fix: "Ensure the accessible name of the element contains the visible label text.",
    });
  }

  // 4.1.2 Name, Role, Value - 17 violations
  for (let i = 0; i < 17; i++) {
    violations.push({
      rule_id: `aria-roles-${i}`,
      wcag_sc: "4.1.2",
      criterion_name: "Name, Role, Value",
      level: "A",
      severity: i < 4 ? "critical" : i < 10 ? "high" : "medium",
      source: i < 8 ? "axe" : "python",
      reason: `Element with role="${["button", "link", "tab", "checkbox"][i % 4]}" is missing required accessible name`,
      element_html: `<div role="${["button", "link", "tab", "checkbox"][i % 4]}" class="custom-control-${i}"></div>`,
      suggested_fix: "Add an aria-label, aria-labelledby, or visible text content to provide an accessible name.",
      help_url: "https://dequeuniversity.com/rules/axe/4.6/aria-roles",
    });
  }

  // 2.5.8 Target Size - 17 violations
  for (let i = 0; i < 17; i++) {
    violations.push({
      rule_id: `target-size-${i}`,
      wcag_sc: "2.5.8",
      criterion_name: "Target Size",
      level: "AA",
      severity: i < 3 ? "high" : i < 10 ? "medium" : "low",
      source: "python",
      reason: `Interactive target is ${12 + i}x${12 + i}px, below the minimum 24x24px requirement`,
      element_html: `<a href="/page-${i}" style="padding:2px" class="small-link">Link</a>`,
      suggested_fix: "Increase the target size to at least 24x24 CSS pixels, or ensure adequate spacing around the target.",
    });
  }

  // 1.3.1 Info and Relationships - 14 violations
  for (let i = 0; i < 14; i++) {
    violations.push({
      rule_id: `structure-${i}`,
      wcag_sc: "1.3.1",
      criterion_name: "Info and Relationships",
      level: "A",
      severity: i < 4 ? "high" : "medium",
      source: i < 7 ? "axe" : "python",
      reason: `${["Form field missing associated label", "Table missing header cells", "List items not in list container", "Heading hierarchy skipped"][i % 4]}`,
      element_html: `<input type="text" class="form-input-${i}">`,
      suggested_fix: "Ensure that information, structure, and relationships conveyed through presentation can be programmatically determined.",
      help_url: "https://dequeuniversity.com/rules/axe/4.6/label",
    });
  }

  // 2.2.2 Pause, Stop, Hide - 2 violations
  for (let i = 0; i < 2; i++) {
    violations.push({
      rule_id: `pause-stop-${i}`,
      wcag_sc: "2.2.2",
      criterion_name: "Pause, Stop, Hide",
      level: "A",
      severity: "high",
      source: "python",
      reason: "Auto-playing carousel does not provide a pause mechanism",
      element_html: `<div class="carousel-container" data-autoplay="true"></div>`,
      suggested_fix: "Provide a mechanism to pause, stop, or hide any auto-updating or moving content.",
    });
  }

  // 3.3.2 Labels or Instructions - 1 violation
  violations.push({
    rule_id: "labels-instructions-0",
    wcag_sc: "3.3.2",
    criterion_name: "Labels or Instructions",
    level: "A",
    severity: "low",
    source: "axe",
    reason: "Search input does not have a visible label or instructions",
    element_html: `<input type="search" placeholder="Search..." class="search-box">`,
    suggested_fix: "Provide visible labels or instructions for user input fields.",
    help_url: "https://dequeuniversity.com/rules/axe/4.6/label",
  });

  return violations;
};

const generateNeedsReview = (): AuditNeedsReview[] => {
  const items: AuditNeedsReview[] = [];
  for (let i = 0; i < 14; i++) {
    items.push({
      rule_id: `review-color-contrast-${i}`,
      wcag_sc: "1.4.3",
      criterion_name: "Contrast (Minimum)",
      level: "AA",
      severity: i < 4 ? "high" : i < 10 ? "medium" : "low",
      source: "axe",
      reason: `Element has insufficient color contrast ratio of ${(3 + i * 0.2).toFixed(1)}:1 (expected 4.5:1 for normal text)`,
      element_html: `<span style="color:#${(777777 + i * 11111).toString(16).slice(0, 6)}; background:#fff" class="text-${i}">Sample text</span>`,
      suggested_fix: "Increase the contrast ratio between the text color and background color to at least 4.5:1 for normal text.",
      help_url: "https://dequeuniversity.com/rules/axe/4.6/color-contrast",
    });
  }
  return items;
};

const generatePasses = (): AuditPass[] => {
  const passes: AuditPass[] = [];
  const axeRules = [
    { id: "html-has-lang", sc: "3.1.1", name: "Language of Page", level: "A" as const },
    { id: "html-lang-valid", sc: "3.1.1", name: "Language of Page", level: "A" as const },
    { id: "document-title", sc: "2.4.2", name: "Page Titled", level: "A" as const },
    { id: "bypass", sc: "2.4.1", name: "Bypass Blocks", level: "A" as const },
    { id: "link-name", sc: "4.1.2", name: "Name, Role, Value", level: "A" as const },
    { id: "heading-order", sc: "1.3.1", name: "Info and Relationships", level: "A" as const },
    { id: "color-contrast-pass", sc: "1.4.3", name: "Contrast (Minimum)", level: "AA" as const },
    { id: "meta-viewport", sc: "1.4.4", name: "Resize Text", level: "AA" as const },
  ];

  // 40 axe passes
  for (let i = 0; i < 40; i++) {
    const rule = axeRules[i % axeRules.length];
    passes.push({
      rule_id: `${rule.id}-pass-${i}`,
      wcag_sc: rule.sc,
      criterion_name: rule.name,
      level: rule.level,
      source: "axe",
      reason: `Element passes ${rule.name} check`,
    });
  }

  const pythonRules = [
    { id: "alt-text-valid", sc: "1.1.1", name: "Non-text Content", level: "A" as const },
    { id: "form-label-valid", sc: "1.3.1", name: "Info and Relationships", level: "A" as const },
    { id: "focus-visible-pass", sc: "2.4.7", name: "Focus Visible", level: "AA" as const },
    { id: "keyboard-accessible", sc: "2.1.1", name: "Keyboard", level: "A" as const },
    { id: "text-spacing-pass", sc: "1.4.12", name: "Text Spacing", level: "AA" as const },
    { id: "reflow-pass", sc: "1.4.10", name: "Reflow", level: "AA" as const },
  ];

  // 261 python passes
  for (let i = 0; i < 261; i++) {
    const rule = pythonRules[i % pythonRules.length];
    passes.push({
      rule_id: `${rule.id}-pass-${i}`,
      wcag_sc: rule.sc,
      criterion_name: rule.name,
      level: rule.level,
      source: "python",
      reason: `Element passes ${rule.name} validation`,
    });
  }

  return passes;
};

export const sampleAuditResult: AuditResult = {
  job_id: "b5ea3ea7-2808-4f31-b589-f3624faaf6ce",
  status: "completed",
  url: "https://www.kao.com/global/en/",
  generated_at: new Date().toISOString(),
  total: 415,
  violations_count: 100,
  needs_review_count: 14,
  passes_count: 301,
  violations: generateViolations(),
  needs_review: generateNeedsReview(),
  passes: generatePasses(),
};
