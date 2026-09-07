"use client";

import { useId, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import {
  replaceExternalProductsAction,
  requestCountryAction,
  requestExternalProductAction,
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

// The three compact forms share state and one status message; splitting them adds prop plumbing only.
// eslint-disable-next-line max-lines-per-function
export function ExternalProductManager(props: Props) {
  const t = useTranslations("objects");
  const headingId = useId();
  const [products] = useState(props.initialProducts);
  const [selected, setSelected] = useState(new Set(props.selectedDomains));
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [countries, setCountries] = useState("");
  const [descriptionRu, setDescriptionRu] = useState("");
  const [descriptionEn, setDescriptionEn] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [countryCode, setCountryCode] = useState("");
  const [countryNameRu, setCountryNameRu] = useState("");
  const [countryNameEn, setCountryNameEn] = useState("");
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
  function requestService() {
    startTransition(async () => {
      const result = await requestExternalProductAction({
        ...common,
        name,
        primaryUrl: url,
        descriptionRu,
        descriptionEn,
        sourceUrl,
        countryCodes: countries
          .split(",")
          .map((value) => value.trim().toUpperCase())
          .filter(Boolean),
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      setName("");
      setUrl("");
      setCountries("");
      setDescriptionRu("");
      setDescriptionEn("");
      setSourceUrl("");
      setMessage(`${t("externalRequested")} ${result.caseId}`);
    });
  }
  function requestCountry() {
    startTransition(async () => {
      const result = await requestCountryAction({
        ...common,
        code: countryCode.trim().toUpperCase(),
        nameRu: countryNameRu,
        nameEn: countryNameEn,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      setCountryCode("");
      setCountryNameRu("");
      setCountryNameEn("");
      setMessage(`${t("countryRequested")} ${result.caseId}`);
    });
  }
  return (
    <section className="space-y-4 rounded-lg border p-4" aria-labelledby={headingId}>
      <div>
        <h2 id={headingId} className="text-lg font-medium">
          {t("externalTitle")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("externalHint")}</p>
      </div>
      <fieldset className="space-y-3">
        <legend className="font-medium">{t("externalLinkedHeading")}</legend>
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
      </fieldset>
      <fieldset className="space-y-3 border-t pt-4">
        <legend className="font-medium">{t("externalRequestHeading")}</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span>{t("externalName")}</span>
            <Input
              placeholder={t("externalNamePlaceholder")}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("externalDescriptionRu")}</span>
            <Input
              value={descriptionRu}
              onChange={(event) => {
                setDescriptionRu(event.target.value);
              }}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("externalDescriptionEn")}</span>
            <Input
              value={descriptionEn}
              onChange={(event) => {
                setDescriptionEn(event.target.value);
              }}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("externalSourceUrl")}</span>
            <Input
              value={sourceUrl}
              onChange={(event) => {
                setSourceUrl(event.target.value);
              }}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("externalUrl")}</span>
            <Input
              placeholder={t("externalUrlPlaceholder")}
              value={url}
              onChange={(event) => {
                setUrl(event.target.value);
              }}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("externalCountries")}</span>
            <Input
              placeholder={t("externalCountriesPlaceholder")}
              value={countries}
              onChange={(event) => {
                setCountries(event.target.value);
              }}
            />
          </label>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={requestService}
          disabled={pending || !name || !url || !descriptionRu || !descriptionEn || !sourceUrl}
        >
          {t("externalRequest")}
        </Button>
      </fieldset>
      <fieldset className="space-y-3 border-t pt-4">
        <legend className="font-medium">{t("countryRequestHeading")}</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span>{t("countryCode")}</span>
            <Input
              value={countryCode}
              onChange={(event) => {
                setCountryCode(event.target.value);
              }}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("countryNameRu")}</span>
            <Input
              value={countryNameRu}
              onChange={(event) => {
                setCountryNameRu(event.target.value);
              }}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("countryNameEn")}</span>
            <Input
              value={countryNameEn}
              onChange={(event) => {
                setCountryNameEn(event.target.value);
              }}
            />
          </label>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={requestCountry}
          disabled={
            pending || !/^[A-Za-z]{2}$/.test(countryCode) || !countryNameRu || !countryNameEn
          }
        >
          {t("countryRequest")}
        </Button>
      </fieldset>
      {message ? (
        <p role="status" className="text-sm">
          {message}
        </p>
      ) : null}
    </section>
  );
}
