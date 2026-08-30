"""Canonical Markdown for one active SEO revision (SPEC-053 REQ-5318)."""

from __future__ import annotations

from ai_stp_contracts.seo import SeoProfileDocument


def render_subject_markdown(profile: SeoProfileDocument) -> str:
    """Render the LLM-readable document from the same profile HTML uses."""
    lines = [
        f"# {profile.heading}",
        "",
        profile.summary,
        "",
        f"canonical: {profile.canonical_url}",
        f"locale: {profile.locale}",
        f"robots: {profile.robots}",
        "",
    ]
    for section in profile.sections:
        lines.extend([f"## {section.heading}", "", section.body, ""])
    if profile.internal_links:
        lines.append("## Links")
        lines.append("")
        for link in profile.internal_links:
            lines.append(f"- [{link.text}]({link.href})")
        lines.append("")
    return "\n".join(lines)
