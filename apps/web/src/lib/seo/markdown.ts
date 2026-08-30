import type { SeoPublicProfile } from "@/lib/api/seo";

export function renderSeoMarkdown(profile: SeoPublicProfile): string {
  const lines = [
    `# ${profile.profile.heading}`,
    "",
    profile.profile.summary,
    "",
    `canonical: ${profile.profile.canonical_url}`,
    "",
  ];
  for (const section of profile.profile.sections) {
    lines.push(`## ${section.heading}`, "", section.body, "");
  }
  if (profile.profile.internal_links.length > 0) {
    lines.push("## Links", "");
    for (const link of profile.profile.internal_links) {
      lines.push(`- [${link.text}](${link.href})`);
    }
    lines.push("");
  }
  return lines.join("\n");
}
