import type { CrawlDepth } from "./crawlDepth";

export interface CombinedAuditParams {
  url: string;
  maxDepth: CrawlDepth;
  wcagLevel: string;
  lang: string;
  email?: string;
}

/**
 * The Python API's `POST {base}/combined-audit` URL. `max_depth` is always
 * sent — including 0, which must not be dropped as "empty" — so the backend
 * never has to guess. `email` is only sent when the user supplied one.
 */
export function buildCombinedAuditUrl(apiBase: string, params: CombinedAuditParams): URL {
  const submitUrl = new URL(`${apiBase}/combined-audit`);
  submitUrl.searchParams.set("url", params.url);
  submitUrl.searchParams.set("max_depth", String(params.maxDepth));
  submitUrl.searchParams.set("wcag_level", params.wcagLevel);
  submitUrl.searchParams.set("lang", params.lang);
  const email = params.email?.trim();
  if (email) submitUrl.searchParams.set("email", email);
  return submitUrl;
}
