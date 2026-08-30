import { describe, expect, it } from "vitest";

import { metadataFromSeo, versionPageMetadata } from "@/lib/seo/metadata";
import { renderSeoMarkdown } from "@/lib/seo/markdown";
import type { SeoPublicProfile } from "@/lib/api/seo";

const profile: SeoPublicProfile = {
  schema_version: 1,
  revision_id: "revision_" + "a".repeat(64),
  snapshot_id: "sha256:" + "b".repeat(64),
  generation: 1,
  etag: "sha256:" + "c".repeat(64),
  profile: {
    canonical_url: "https://example.test/en/catalog/components/cid",
    title: "Demo skill — component",
    description: "Public skill for catalog search and install.",
    heading: "Demo skill",
    summary: "Public skill for catalog search and install.",
    robots: "index,follow",
    alternates: { en: "https://example.test/en/catalog/components/cid" },
    json_ld: {
      "@context": "https://schema.org",
      "@graph": [{ "@type": "Person", name: "Ada Lovelace" }],
    },
    social: {
      title: "Demo skill — component",
      description: "Public skill for catalog search and install.",
      image_url: "https://example.test/og/revision.png",
      image_alt: "Demo skill",
      locale: "en",
    },
    sections: [
      { id: "purpose", heading: "Purpose", body: "Public skill.", provenance: "template" },
    ],
    internal_links: [
      { rel: "related", href: "https://example.test/en/catalog/setups/sid", text: "Setup" },
    ],
    breadcrumbs: [{ rel: "home", href: "https://example.test/en", text: "Home" }],
    index_decision: { eligible: true, reasons: ["eligible"] },
    modified_at: "2026-08-01T00:00:00.000Z",
    published_at: "2026-08-01T00:00:00.000Z",
  },
};

describe("seo metadata projection", () => {
  it("maps the active profile onto metadata, OG and twitter", () => {
    const meta = metadataFromSeo(profile, { title: "fallback" });
    expect(meta.title).toEqual({ absolute: profile.profile.title });
    expect(meta.alternates?.canonical).toBe(profile.profile.canonical_url);
    expect(meta.alternates?.languages).toMatchObject({
      en: profile.profile.canonical_url,
      "x-default": profile.profile.canonical_url,
    });
    expect(meta.authors).toEqual([{ name: "Ada Lovelace" }]);
    expect(meta.creator).toBe("Ada Lovelace");
    expect(meta.robots).toEqual({ index: true, follow: true });
    const images = meta.openGraph?.images;
    const first = Array.isArray(images) ? images[0] : images;
    expect(first).toMatchObject({ width: 1200, height: 630 });
    const twitterImages = meta.twitter?.images;
    const twitterImage = Array.isArray(twitterImages) ? twitterImages[0] : twitterImages;
    expect(twitterImage).toMatchObject({ alt: profile.profile.social.image_alt });
  });

  it("keeps a valid fallback indexable when the active revision is temporarily missing", () => {
    const meta = metadataFromSeo(null, { title: "fallback" });
    expect(meta.title).toBe("fallback");
    expect(meta.robots).toEqual({ index: true, follow: true });
  });

  it("keeps version pages from becoming independent canonicals", () => {
    const meta = versionPageMetadata("/en/catalog/components/cid", "Demo skill@1.0");
    expect(meta.title).toBe("Demo skill@1.0");
    expect(meta.alternates?.canonical).toBe("/en/catalog/components/cid");
    expect(meta.robots).toEqual({ index: false, follow: true });
  });

  it("renders markdown from the same profile as HTML", () => {
    const markdown = renderSeoMarkdown(profile);
    expect(markdown).toContain("# Demo skill");
    expect(markdown).toContain("canonical: https://example.test/en/catalog/components/cid");
    expect(markdown).toContain("[Setup](https://example.test/en/catalog/setups/sid)");
    expect(markdown).not.toContain("<script");
  });
});
