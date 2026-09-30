type SeoJsonLdProps = {
  jsonLd: unknown;
};

export function SeoJsonLd({ jsonLd }: SeoJsonLdProps) {
  return (
    <script
      type="application/ld+json"
      // `application/ld+json` content is raw text, not HTML-parsed, so the
      // only breakout is a literal `</script` — and every `<` is escaped to
      // a unicode escape first, so one cannot form. CodeQL cannot see the
      // total replaceAll.
      // codeql[js/xss]
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replaceAll("<", "\\u003c") }}
    />
  );
}
