"use client";

import { useState, useTransition } from "react";

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
      setMessage(result.ok ? "Services saved." : result.message);
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
          .map((v) => v.trim().toUpperCase())
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
      setMessage("Service created. Save to attach it.");
    });
  }
  return (
    <section
      className="space-y-4 rounded-lg border p-4"
      aria-labelledby="external-products-heading"
    >
      <div>
        <h2 id="external-products-heading" className="text-lg font-medium">
          External services
        </h2>
        <p className="text-muted-foreground text-sm">
          Mutable catalog metadata; it does not change the version digest.
        </p>
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
        Save services
      </Button>
      <div className="grid gap-2 border-t pt-4 sm:grid-cols-3">
        <Input
          aria-label="Service name"
          placeholder="Kaspi"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
          }}
        />
        <Input
          aria-label="Primary HTTPS URL"
          placeholder="https://kaspi.kz/shop"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
          }}
        />
        <Input
          aria-label="Country codes"
          placeholder="KZ, RU"
          value={countries}
          onChange={(e) => {
            setCountries(e.target.value);
          }}
        />
      </div>
      <Button type="button" variant="outline" onClick={create} disabled={pending || !name || !url}>
        Create service
      </Button>
      {message ? (
        <p role="status" className="text-sm">
          {message}
        </p>
      ) : null}
    </section>
  );
}
