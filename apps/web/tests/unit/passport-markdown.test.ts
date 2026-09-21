import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  MarkdownPolicyError,
  projectSafeMarkdown,
  renderPassportDescription,
} from "@/lib/markdown/passport";

type AcceptedCase = { id: string; source: string; html: string; excerpt: string };
type RejectedCase = { id: string; source: string; code: string };
type Corpus = {
  description_format: string;
  renderer_version: string;
  accepted: AcceptedCase[];
  rejected: RejectedCase[];
};

// REQ-2908: the web consumes the same corpus file — no copy.
const corpusPath = path.resolve(
  __dirname,
  "../../../../packages/passports/src/ai_stp_passports/fixtures/safe-markdown-v1.json",
);
const corpus = JSON.parse(readFileSync(corpusPath, "utf8")) as Corpus;

describe("projectSafeMarkdown shared corpus (SPEC-029)", () => {
  it.each(corpus.accepted.map((c) => [c.id, c] as const))(
    "accepted case %s renders exact html and excerpt",
    (_id, c) => {
      const projection = projectSafeMarkdown(c.source);
      expect(projection.description_format).toBe(corpus.description_format);
      expect(projection.renderer_version).toBe(corpus.renderer_version);
      expect(projection.html).toBe(c.html);
      expect(projection.excerpt).toBe(c.excerpt);
    },
  );

  it.each(corpus.rejected.map((c) => [c.id, c] as const))(
    "rejected case %s fails with its stable code",
    (_id, c) => {
      try {
        projectSafeMarkdown(c.source);
        expect.unreachable(`case ${c.id} must be rejected`);
      } catch (error) {
        expect(error).toBeInstanceOf(MarkdownPolicyError);
        expect((error as MarkdownPolicyError).code).toBe(c.code);
      }
    },
  );
});

describe("renderPassportDescription", () => {
  it("renders valid source", () => {
    expect(renderPassportDescription("Hello **world**")).toContain("<strong>world</strong>");
  });

  it("fails closed to escaped text instead of throwing", () => {
    const html = renderPassportDescription("x <script>alert(1)</script>");
    expect(html).not.toContain("<script");
    expect(html).toContain("&lt;script&gt;");
  });

  it("rejects an unknown renderer version", () => {
    expect(() => projectSafeMarkdown("text", "safe_markdown_v2")).toThrowError(MarkdownPolicyError);
  });
});
