import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildCombinedAuditUrl } from "./combinedAuditUrl.ts";

const BASE = "https://api.example.test/api/v1/combined";

describe("buildCombinedAuditUrl", () => {
  it("sends depth 0 explicitly rather than dropping it as empty", () => {
    const url = buildCombinedAuditUrl(BASE, { url: "https://example.com", maxDepth: 0, wcagLevel: "AA", lang: "en" });
    assert.equal(url.searchParams.get("max_depth"), "0");
  });

  it("sends the selected depth and the other fields", () => {
    const url = buildCombinedAuditUrl(BASE, {
      url: "https://example.com/a?b=1",
      maxDepth: 2,
      wcagLevel: "AAA",
      lang: "ja",
      email: "  someone@example.com ",
    });
    assert.equal(url.pathname, "/api/v1/combined/combined-audit");
    assert.equal(url.searchParams.get("url"), "https://example.com/a?b=1");
    assert.equal(url.searchParams.get("max_depth"), "2");
    assert.equal(url.searchParams.get("wcag_level"), "AAA");
    assert.equal(url.searchParams.get("lang"), "ja");
    assert.equal(url.searchParams.get("email"), "someone@example.com");
  });

  it("omits a blank email", () => {
    const url = buildCombinedAuditUrl(BASE, { url: "https://example.com", maxDepth: 1, wcagLevel: "AA", lang: "en", email: "  " });
    assert.equal(url.searchParams.has("email"), false);
  });
});
