"use client";

import { useState } from "react";
import { Input } from "@/components/atoms/input";
import { Link } from "@/lib/i18n/navigation";

type Result = { id: string; url: string; content: string };

export function DocsSearch({ locale }: { locale: string }) {
  const [results, setResults] = useState<Result[]>([]);
  return (
    <div className="space-y-2">
      <Input
        type="search"
        placeholder={locale === "ru" ? "Поиск по документации" : "Search documentation"}
        aria-label={locale === "ru" ? "Поиск по документации" : "Search documentation"}
        onChange={(event) => {
          const query = event.target.value.trim();
          if (query.length < 2) {
            setResults([]);
            return;
          }
          void fetch(`/api/docs-search?query=${encodeURIComponent(query)}`)
            .then((response) => response.json())
            .then((body: unknown) => {
              const items = Array.isArray(body) ? body : [];
              setResults(
                (items as Result[]).filter((item) => item.url.includes(`/${locale}/`)).slice(0, 6),
              );
            });
        }}
      />
      {results.length ? (
        <ul className="border-border bg-popover rounded-md border p-1 text-sm">
          {results.map((item) => (
            <li key={`${item.id}-${item.url}`}>
              <Link
                href={item.url.replace(`/docs/${locale}`, "/docs")}
                className="hover:bg-muted block rounded-sm px-2 py-2"
              >
                {item.content}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
