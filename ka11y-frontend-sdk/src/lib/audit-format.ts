const BEST_PRACTICE_ID = "best-practice";

export function formatCriterionId(value: string | null | undefined): string {
  if (!value) return "unmapped";
  return value;
}

export function formatCriterionName(
  value: string | null | undefined,
  wcagSc: string | null | undefined,
): string {
  if (value && value.trim()) return value;
  if (wcagSc === BEST_PRACTICE_ID) return "Best Practice";
  if (wcagSc) return `WCAG ${wcagSc}`;
  return "Unmapped criterion";
}

export function formatLevel(value: string | null | undefined): string {
  return value && value.trim() ? value : "—";
}

export function formatElementSnippet(value: string | null | undefined): string {
  return value && value.trim() ? value : "No element snippet available";
}

export function formatElementTag(value: string | null | undefined): string {
  return value && value.trim() ? value.toLowerCase() : "—";
}
