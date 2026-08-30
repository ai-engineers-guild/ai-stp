type SeoJsonLdProps = {
  jsonLd: unknown;
};

export function SeoJsonLd({ jsonLd }: SeoJsonLdProps) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replaceAll("<", "\\u003c") }}
    />
  );
}
