export type WcagLevel = "A" | "AA" | "AAA";

export interface SummaryTotals {
  violations: number;
  needsReview: number;
  passes: number;
}

export interface WcagLevelBreakdown {
  level: WcagLevel;
  violations: number;
  needsReview: number;
  passes: number;
}

export interface FailingCriterion {
  code: string;
  label: string;
  level: WcagLevel;
  count: number;
}

export interface PageFinding {
  pageName: string;
  url: string;
  score: number;
  findings: number;
  violations: number;
  needsReview: number;
  passes: number;
}

export const summaryTotals: SummaryTotals = {
  violations: 74,
  needsReview: 441,
  passes: 282,
};

export const sitePerformanceScore = 80;

export const wcagLevelBreakdown: WcagLevelBreakdown[] = [
  { level: "A", violations: 8, needsReview: 30, passes: 40 },
  { level: "AA", violations: 27, needsReview: 165, passes: 45 },
  { level: "AAA", violations: 39, needsReview: 246, passes: 197 },
];

export const topFailingCriteria: FailingCriterion[] = [
  { code: "1.4.3", label: "Contrast(Minimum)", level: "AA", count: 19 },
  { code: "1.4.6", label: "Contrast(Enhanced)", level: "AAA", count: 19 },
  { code: "1.4.5", label: "Images of Text", level: "AA", count: 12 },
  { code: "1.1.1", label: "Non-text Content", level: "A", count: 9 },
  { code: "3.3.2", label: "Labels or Instructions", level: "A", count: 7 },
  { code: "1.4.11", label: "Non-text Contrast", level: "AA", count: 6 },
  { code: "4.1.2", label: "Name, Role, Value", level: "A", count: 3 },
  { code: "1.3.1", label: "Info and Relationships", level: "A", count: 2 },
];

export const pageFindings: PageFinding[] = [
  {
    pageName: "Home Page",
    url: "http://croppico.com/",
    score: 83.1,
    findings: 712,
    violations: 54,
    needsReview: 393,
    passes: 265,
  },
  {
    pageName: "Contact Page",
    url: "http://croppico.com/contact",
    score: 50,
    findings: 45,
    violations: 13,
    needsReview: 19,
    passes: 13,
  },
  {
    pageName: "Privacy Policy",
    url: "http://croppico.com/privacy-policy",
    score: 36.4,
    findings: 40,
    violations: 7,
    needsReview: 29,
    passes: 4,
  },
];

export const auditTarget = "https://samplesite.com/";
