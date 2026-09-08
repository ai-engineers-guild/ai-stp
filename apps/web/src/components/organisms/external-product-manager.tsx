"use client";

/* eslint-disable max-lines -- the service and nested country request flows share one editor surface. */

import { useMemo, useRef, useState, useTransition, type ReactNode } from "react";
import { useTranslations } from "next-intl";

import {
  replaceExternalProductsAction,
  requestCountryAction,
  requestExternalProductAction,
} from "@/actions/external-products";
import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/atoms/dialog";
import { Input } from "@/components/atoms/input";
import type { ExternalProduct } from "@/lib/api/catalog";
import { Icon } from "@/theme";

type Props = {
  locale: string;
  objectKind: "component" | "setup";
  stableId: string;
  csrfToken: string;
  initialProducts: ExternalProduct[];
  selectedDomains: string[];
};

type RequestContext = Pick<Props, "locale" | "objectKind" | "stableId" | "csrfToken">;
type Status = { kind: "success" | "error"; text: string };

const CONTROL_CLASS =
  "border-input bg-background min-h-11 w-full rounded-sm border px-3 py-2 text-sm text-foreground focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none";
const TEXTAREA_CLASS = `${CONTROL_CLASS} min-h-28 resize-y`;

export function ExternalProductManager(props: Props) {
  const t = useTranslations("objects");
  const initialDomain = props.selectedDomains.length === 1 ? (props.selectedDomains[0] ?? "") : "";
  const [selectedDomain, setSelectedDomain] = useState(initialDomain);
  const [selectionTouched, setSelectionTouched] = useState(false);
  const [relationStatus, setRelationStatus] = useState<Status | null>(null);
  const [requestOpen, setRequestOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const common: RequestContext = {
    csrfToken: props.csrfToken,
    locale: props.locale,
    objectKind: props.objectKind,
    stableId: props.stableId,
  };
  const hasMultipleRelations = props.selectedDomains.length > 1;

  function saveSelection() {
    startTransition(async () => {
      const result = await replaceExternalProductsAction({
        ...common,
        canonicalDomains: selectedDomain ? [selectedDomain] : [],
      });
      setRelationStatus(
        result.ok
          ? { kind: "success", text: t("serviceLinkSaved") }
          : { kind: "error", text: result.message },
      );
    });
  }

  return (
    <section className="border-border min-w-0 space-y-4 rounded-lg border p-4">
      <header className="space-y-1">
        <h2 className="text-lg font-medium">{t("servicesEditorTitle")}</h2>
        <p className="text-muted-foreground text-sm">{t("servicesEditorHint")}</p>
      </header>

      {hasMultipleRelations ? (
        <div className="border-border bg-muted/30 rounded-md border p-3 text-sm" role="alert">
          <p>{t("multipleServicesWarning")}</p>
          <p className="text-muted-foreground mt-1 font-mono text-xs break-all">
            {props.selectedDomains.join(", ")}
          </p>
        </div>
      ) : null}

      <div className="flex min-w-0 items-end gap-2">
        <ServiceSelector
          products={props.initialProducts}
          selectedDomain={selectedDomain}
          onChange={(domain) => {
            setSelectedDomain(domain);
            setSelectionTouched(true);
            setRelationStatus(null);
          }}
          labels={{
            field: t("serviceSelectorLabel"),
            none: t("serviceNone"),
            search: t("serviceSearch"),
            noResults: t("serviceNoResults"),
            noOptions: t("serviceNoOptions"),
            countries: t("serviceCountries"),
          }}
        />
        <AddButton
          label={t("addService")}
          onClick={() => {
            setRequestOpen(true);
          }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          onClick={saveSelection}
          disabled={pending || (hasMultipleRelations && !selectionTouched)}
        >
          {t("saveServiceLink")}
        </Button>
        {relationStatus ? (
          <p
            className={`text-sm ${relationStatus.kind === "error" ? "text-destructive" : "text-muted-foreground"}`}
            role={relationStatus.kind === "error" ? "alert" : "status"}
            aria-live="polite"
          >
            {relationStatus.text}
          </p>
        ) : null}
      </div>

      <ServiceRequestDialog open={requestOpen} onOpenChange={setRequestOpen} context={common} />
    </section>
  );
}

function ServiceSelector({
  products,
  selectedDomain,
  onChange,
  labels,
}: {
  products: ExternalProduct[];
  selectedDomain: string;
  onChange: (domain: string) => void;
  labels: {
    field: string;
    none: string;
    search: string;
    noResults: string;
    noOptions: string;
    countries: string;
  };
}) {
  const [search, setSearch] = useState("");
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const selected = products.find((product) => product.canonical_domain === selectedDomain);
  const filtered = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase();
    if (!normalized) return products;
    return products.filter(
      (product) =>
        product.name.toLocaleLowerCase().includes(normalized) ||
        product.canonical_domain.toLocaleLowerCase().includes(normalized),
    );
  }, [products, search]);

  function choose(domain: string) {
    onChange(domain);
    detailsRef.current?.removeAttribute("open");
  }

  return (
    <div className="min-w-0 flex-1 space-y-1.5 text-sm font-medium">
      <span className="block">{labels.field}</span>
      <details
        ref={detailsRef}
        className="border-input bg-background relative min-w-0 rounded-sm border"
      >
        <summary className="focus-visible:ring-ring flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-sm marker:content-none focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
          <span className="min-w-0 truncate">
            {selected ? `${selected.name} · ${selected.canonical_domain}` : labels.none}
          </span>
          <Icon name="chevronDown" size="sm" />
        </summary>
        <div className="bg-popover border-border absolute top-[calc(100%+0.375rem)] right-0 left-0 z-50 min-w-0 space-y-2 rounded-sm border p-3 shadow-md">
          <label className="sr-only" htmlFor="service-search">
            {labels.search}
          </label>
          <Input
            id="service-search"
            type="search"
            value={search}
            placeholder={labels.search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
          <div
            className="max-h-64 space-y-1 overflow-y-auto"
            role="radiogroup"
            aria-label={labels.field}
          >
            <label className="hover:bg-muted flex min-h-11 cursor-pointer items-start gap-2 rounded-sm px-2 py-2 text-sm">
              <input
                type="radio"
                name="external-service"
                checked={!selectedDomain}
                onChange={() => {
                  choose("");
                }}
              />
              <span>{labels.none}</span>
            </label>
            {filtered.map((product) => (
              <label
                key={product.canonical_domain}
                className="hover:bg-muted flex min-h-11 cursor-pointer items-start gap-2 rounded-sm px-2 py-2 text-sm"
              >
                <input
                  type="radio"
                  name="external-service"
                  checked={selectedDomain === product.canonical_domain}
                  onChange={() => {
                    choose(product.canonical_domain);
                  }}
                />
                <span className="min-w-0">
                  <span className="block break-words">{product.name}</span>
                  <span className="text-muted-foreground block font-mono text-xs break-all">
                    {product.canonical_domain}
                  </span>
                  {product.country_codes.length ? (
                    <span className="text-muted-foreground mt-1 block text-xs">
                      {labels.countries}: {product.country_codes.join(", ")}
                    </span>
                  ) : null}
                </span>
              </label>
            ))}
            {!products.length ? (
              <p className="text-muted-foreground px-2 py-2 text-sm">{labels.noOptions}</p>
            ) : filtered.length === 0 ? (
              <p className="text-muted-foreground px-2 py-2 text-sm">{labels.noResults}</p>
            ) : null}
          </div>
        </div>
      </details>
    </div>
  );
}

function AddButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="group/add text-foreground hover:bg-accent focus-visible:ring-ring border-input relative grid h-11 w-11 shrink-0 place-items-center rounded-sm border focus-visible:ring-2 focus-visible:outline-none"
      onClick={onClick}
    >
      <Icon name="plus" size="sm" />
      <span
        role="tooltip"
        className="border-border bg-popover text-popover-foreground pointer-events-none absolute right-0 bottom-full z-[70] mb-2 hidden w-max max-w-[min(16rem,calc(100vw-2rem))] rounded-md border p-2 text-left text-xs font-normal shadow-md group-hover/add:block group-focus-visible/add:block"
      >
        {label}
      </span>
    </button>
  );
}

// eslint-disable-next-line max-lines-per-function -- the dialog owns the complete request form and nested country flow.
function ServiceRequestDialog({
  open,
  onOpenChange,
  context,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  context: RequestContext;
}) {
  const t = useTranslations("objects");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [countries, setCountries] = useState("");
  const [descriptionRu, setDescriptionRu] = useState("");
  const [descriptionEn, setDescriptionEn] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [countryOpen, setCountryOpen] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [pending, startTransition] = useTransition();

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    startTransition(async () => {
      const result = await requestExternalProductAction({
        ...context,
        name: name.trim(),
        primaryUrl: url.trim(),
        descriptionRu: descriptionRu.trim(),
        descriptionEn: descriptionEn.trim(),
        sourceUrl: sourceUrl.trim(),
        countryCodes: countries
          .split(",")
          .map((value) => value.trim().toUpperCase())
          .filter(Boolean),
      });
      if (!result.ok) {
        setStatus({ kind: "error", text: result.message });
        return;
      }
      setName("");
      setUrl("");
      setCountries("");
      setDescriptionRu("");
      setDescriptionEn("");
      setSourceUrl("");
      setStatus({ kind: "success", text: t("serviceRequestSuccess", { caseId: result.caseId }) });
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl"
        closeLabel={t("dialogClose")}
      >
        <DialogHeader>
          <DialogTitle>{t("serviceRequestTitle")}</DialogTitle>
          <DialogDescription>{t("serviceRequestHint")}</DialogDescription>
        </DialogHeader>
        <form className="space-y-5" noValidate onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("externalName")} required help={t("serviceRequestNameHelp")}>
              <Input
                value={name}
                required
                placeholder={t("externalNamePlaceholder")}
                onChange={(event) => {
                  setName(event.target.value);
                }}
              />
            </Field>
            <Field label={t("externalUrl")} required help={t("serviceRequestUrlHelp")}>
              <Input
                type="url"
                value={url}
                required
                placeholder={t("externalUrlPlaceholder")}
                onChange={(event) => {
                  setUrl(event.target.value);
                }}
              />
            </Field>
            <Field label={t("externalDescriptionRu")} required>
              <textarea
                className={TEXTAREA_CLASS}
                value={descriptionRu}
                required
                onChange={(event) => {
                  setDescriptionRu(event.target.value);
                }}
              />
            </Field>
            <Field label={t("externalDescriptionEn")} required>
              <textarea
                className={TEXTAREA_CLASS}
                value={descriptionEn}
                required
                onChange={(event) => {
                  setDescriptionEn(event.target.value);
                }}
              />
            </Field>
            <Field label={t("externalSourceUrl")} required help={t("serviceRequestSourceHelp")}>
              <Input
                type="url"
                value={sourceUrl}
                required
                onChange={(event) => {
                  setSourceUrl(event.target.value);
                }}
              />
            </Field>
            <Field label={t("externalCountries")} help={t("serviceRequestCountriesHelp")}>
              <div className="flex gap-2">
                <Input
                  value={countries}
                  placeholder={t("externalCountriesPlaceholder")}
                  onChange={(event) => {
                    setCountries(event.target.value);
                  }}
                />
                <AddButton
                  label={t("addCountry")}
                  onClick={() => {
                    setCountryOpen(true);
                  }}
                />
              </div>
            </Field>
          </div>

          {status ? (
            <p
              className={`text-sm ${status.kind === "error" ? "text-destructive" : "text-muted-foreground"}`}
              role={status.kind === "error" ? "alert" : "status"}
              aria-live="polite"
            >
              {status.text}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                onOpenChange(false);
              }}
            >
              {t("dialogCancel")}
            </Button>
            <Button type="submit" disabled={pending} aria-busy={pending}>
              {t("serviceRequestSubmit")}
            </Button>
          </DialogFooter>
        </form>

        <CountryRequestDialog
          open={countryOpen}
          onOpenChange={setCountryOpen}
          context={context}
          onSuccess={(code, caseId) => {
            setCountries((current) => (current ? `${current}, ${code}` : code));
            setStatus({ kind: "success", text: t("countryRequestSuccess", { caseId }) });
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

function CountryRequestDialog({
  open,
  onOpenChange,
  context,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  context: RequestContext;
  onSuccess: (code: string, caseId: string) => void;
}) {
  const t = useTranslations("objects");
  const [code, setCode] = useState("");
  const [nameRu, setNameRu] = useState("");
  const [nameEn, setNameEn] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [pending, startTransition] = useTransition();

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedCode = code.trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(normalizedCode)) {
      setStatus({ kind: "error", text: t("invalidCountryCode") });
      return;
    }
    startTransition(async () => {
      const result = await requestCountryAction({
        ...context,
        code: normalizedCode,
        nameRu: nameRu.trim(),
        nameEn: nameEn.trim(),
      });
      if (!result.ok) {
        setStatus({ kind: "error", text: result.message });
        return;
      }
      onSuccess(normalizedCode, result.caseId);
      setCode("");
      setNameRu("");
      setNameEn("");
      setStatus(null);
      onOpenChange(false);
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto" closeLabel={t("dialogClose")}>
        <DialogHeader>
          <DialogTitle>{t("countryRequestTitle")}</DialogTitle>
          <DialogDescription>{t("countryRequestHint")}</DialogDescription>
        </DialogHeader>
        <form className="space-y-5" noValidate onSubmit={submit}>
          <div className="space-y-4">
            <Field label={t("countryCode")} required help={t("countryRequestCodeHelp")}>
              <Input
                value={code}
                required
                maxLength={2}
                placeholder={t("countryCodePlaceholder")}
                onChange={(event) => {
                  setCode(event.target.value.toUpperCase());
                }}
              />
            </Field>
            <Field label={t("countryNameRu")} required>
              <Input
                value={nameRu}
                required
                onChange={(event) => {
                  setNameRu(event.target.value);
                }}
              />
            </Field>
            <Field label={t("countryNameEn")} required>
              <Input
                value={nameEn}
                required
                onChange={(event) => {
                  setNameEn(event.target.value);
                }}
              />
            </Field>
          </div>
          {status ? (
            <p className="text-destructive text-sm" role="alert">
              {status.text}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                onOpenChange(false);
              }}
            >
              {t("dialogCancel")}
            </Button>
            <Button type="submit" disabled={pending} aria-busy={pending}>
              {t("countryRequestSubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  help,
  required = false,
  children,
}: {
  label: string;
  help?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="min-w-0 space-y-1.5 text-sm">
      <span className="block font-medium">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </span>
      {children}
      {help ? (
        <span className="text-muted-foreground block text-xs leading-relaxed">{help}</span>
      ) : null}
    </label>
  );
}
