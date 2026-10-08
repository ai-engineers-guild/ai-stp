"use client";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";

import { Label } from "@/components/atoms/label";

import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/atoms/dialog";

import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";

import { type TechnologyReviewState } from "@/lib/technology-review-state";
export function TechnologyReviewDialogs({ state }: { state: TechnologyReviewState }) {
  const {
    categories,
    areas,
    t,
    w,
    active,
    authority,
    pendingOnly,
    create,
    evidence,
    advanced,
    patch,
    setPendingOnly,
    setPage,
    setCreate,
    setEvidence,
    setAdvanced,
  } = state;
  const s = useTranslations("technology.scans");
  const k = useTranslations("technology.scans.versionKind");
  const kinds = {
    unknown: k("unknown"),
    declared_range: k("declared_range"),
    observed_version: k("observed_version"),
  };
  return (
    <>
      <Dialog
        open={create !== null}
        onOpenChange={(open) => {
          if (!open) setCreate(null);
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogTitle>
            {t(
              create === "category"
                ? "createCategory"
                : create === "area"
                  ? "areas.create"
                  : "createTechnology",
            )}
          </DialogTitle>
          <DialogDescription>{w("createDescription")}</DialogDescription>
          {create && (
            <TechnologyRegistryCreate
              kind={create}
              {...authority}
              authorizationRevision={String(authority.authorizationRevision)}
              categories={categories?.filter((item) => item.state !== "archived") ?? null}
              areas={areas?.filter((item) => item.state !== "archived") ?? null}
              onCreated={(record) => {
                if (active) {
                  if (typeof record.technology_id === "string")
                    patch(active, { technology: record.technology_id });
                  if (typeof record.category_id === "string")
                    patch(active, { category: record.category_id });
                }
                setCreate(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={evidence !== null}
        onOpenChange={(open) => {
          if (!open) setEvidence(null);
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
          <DialogTitle>{w("evidence")}</DialogTitle>
          <DialogDescription>{evidence?.coordinate}</DialogDescription>
          {evidence && (
            <p className="text-sm">
              {w("versions")}: {evidence.version ?? "—"} · {kinds[evidence.version_kind]}
            </p>
          )}
          <dl className="space-y-3 text-sm">
            {evidence?.evidence.map((entry, index) => (
              <div key={index} className="border-border space-y-1 border-b pb-3">
                <dt className="font-medium break-all">
                  {entry.path ?? entry.reference ?? entry.source}
                </dt>
                <dd className="text-muted-foreground break-all">
                  {entry.reference} · {entry.source_revision?.slice(0, 12) ?? "—"}
                </dd>
                <dd>{w("confidence", { count: Math.round((entry.confidence ?? 0) * 100) })}</dd>
                <dd>
                  {s("detectorVersion", { version: entry.detector_version ?? "—" })} ·{" "}
                  {s("mappingVersion", { version: entry.mapping_version ?? "—" })}
                </dd>
              </div>
            ))}
          </dl>
        </DialogContent>
      </Dialog>
      <Dialog open={advanced} onOpenChange={setAdvanced}>
        <DialogContent>
          <DialogTitle>{t("filters")}</DialogTitle>
          <DialogDescription>{w("filterDescription")}</DialogDescription>
          <Label className="flex min-h-11 items-center gap-2">
            <input
              type="checkbox"
              checked={pendingOnly}
              onChange={(e) => {
                setPendingOnly(e.target.checked);
                setPage(1);
              }}
            />
            {w("pendingOnly")}
          </Label>
          <Button
            onClick={() => {
              setAdvanced(false);
            }}
          >
            {t("apply")}
          </Button>
        </DialogContent>
      </Dialog>
    </>
  );
}
