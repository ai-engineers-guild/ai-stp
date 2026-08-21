"use client";

import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import {
  createExternalProductAction,
  replaceExternalProductsAction,
} from "@/actions/external-products";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import type { ExternalProduct } from "@/lib/api/catalog";

type Props = {
  locale: string;
  objectKind: "component" | "setup";
  stableId: string;
  csrfToken: string;
  initialProducts: ExternalProduct[];
  selectedDomains: string[];
};

export function ExternalProductManager(props: Props) {
  const t = useTranslations("objects");
  const [products, setProducts] = useState(props.initialProducts);
  const [selected, setSelected] = useState(new Set(props.selectedDomains));
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [countries, setCountries] = useState("");
  const [message, setMessage] = useState("");
  const [pending, startTransition] = useTransition();
  const common = {
    csrfToken: props.csrfToken,
    locale: props.locale,
    objectKind: props.objectKind,
    stableId: props.stableId,
  };
  function save() {
    startTransition(async () => {
      const result = await replaceExternalProductsAction({
        ...common,
        canonicalDomains: [...selected],
      });
      setMessage(result.ok ? t("externalSaved") : result.message);
    });
  }
  function create() {
    startTransition(async () => {
      const result = await createExternalProductAction({
        ...common,
        name,
        primaryUrl: url,
        countryCodes: countries
          .split(",")
          .map((value) => value.trim().toUpperCase())
          .filter(Boolean),
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      setProducts((items) =>
        [...items, result.product].sort((a, b) => a.name.localeCompare(b.name)),
      );
      setSelected((items) => new Set(items).add(result.product.canonical_domain));
      setName("");
      setUrl("");
      setCountries("");
      setMessage(t("externalCreated"));
    });
  }
  return (
    <section
      className="space-y-4 rounded-lg border p-4"
      aria-labelledby="external-products-heading"
    >
      <div>
        <h2 id="external-products-heading" className="text-lg font-medium">
          {t("externalTitle")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("externalHint")}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {products.map((product) => (
          <label
            className="flex items-center gap-2 rounded border px-3 py-2"
            key={product.canonical_domain}
          >
            <input
              type="checkbox"
              checked={selected.has(product.canonical_domain)}
              onChange={(event) => {
                setSelected((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.add(product.canonical_domain);
                  else next.delete(product.canonical_domain);
                  return next;
                });
              }}
            />
            <span>
              {product.name}{" "}
              <small className="text-muted-foreground">{product.canonical_domain}</small>
            </span>
          </label>
        ))}
      </div>
      <Button type="button" onClick={save} disabled={pending}>
        {t("externalSave")}
      </Button>
      <div className="grid gap-2 border-t pt-4 sm:grid-cols-3">
        <Input
          aria-label={t("externalName")}
          placeholder={t("externalNamePlaceholder")}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
        <Input
          aria-label={t("externalUrl")}
          placeholder={t("externalUrlPlaceholder")}
          value={url}
          onChange={(event) => {
            setUrl(event.target.value);
          }}
        />
        <Input
          aria-label={t("externalCountries")}
          placeholder={t("externalCountriesPlaceholder")}
          value={countries}
          onChange={(event) => {
            setCountries(event.target.value);
          }}
        />
      </div>
      <Button type="button" variant="outline" onClick={create} disabled={pending || !name || !url}>
        {t("externalCreate")}
      </Button>
      {message ? (
        <p role="status" className="text-sm">
          {message}
        </p>
      ) : null}
    </section>
  );
}
