"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  corporateMutationAction,
  corporateCatalogVersionsAction,
  corporateSubjectSearchAction,
  type CorporateAssignContext,
  type CorporateAssignSubjectKind,
} from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/atoms/dialog";
import { Label } from "@/components/atoms/label";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";

const SUBJECT_KINDS: CorporateAssignSubjectKind[] = ["employee", "team", "project", "technology"];

type SubjectOption = { value: string; label: string };
type SubjectOptions = Record<CorporateAssignSubjectKind, SubjectOption[]>;
type SubjectSelection = Record<CorporateAssignSubjectKind, string[]>;

const EMPTY_SELECTION: SubjectSelection = {
  employee: [],
  team: [],
  project: [],
  technology: [],
};

const EMPTY_OPTIONS: SubjectOptions = {
  employee: [],
  team: [],
  project: [],
  technology: [],
};

type CorporateAssignDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  context: Extract<CorporateAssignContext, { ok: true }>;
  objectKind: "setup" | "component";
  stableId: string;
  objectName: string;
};

// eslint-disable-next-line max-lines-per-function
export function CorporateAssignDialog({
  open,
  onOpenChange,
  context,
  objectKind,
  stableId,
  objectName,
}: CorporateAssignDialogProps) {
  const h = context.labels;
  const router = useRouter();
  const [versions, setVersions] = useState<string[]>([]);
  const [version, setVersion] = useState("latest");
  const [options, setOptions] = useState<SubjectOptions>(EMPTY_OPTIONS);
  const [selected, setSelected] = useState<SubjectSelection>(EMPTY_SELECTION);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const loaded = useRef(false);

  async function load() {
    const { organizationId, csrfToken } = context;
    setLoading(true);
    const [versionResult, ...subjectResults] = await Promise.all([
      corporateCatalogVersionsAction({ kind: objectKind, id: stableId, csrfToken }),
      ...SUBJECT_KINDS.map((kind) =>
        corporateSubjectSearchAction({ organizationId, kind, csrfToken }),
      ),
    ]);
    if (versionResult.ok) setVersions(versionResult.versions);
    setOptions(
      Object.fromEntries(
        SUBJECT_KINDS.map((kind, index) => {
          const result = subjectResults[index];
          return [kind, result?.ok ? result.items : []];
        }),
      ) as SubjectOptions,
    );
    setLoading(false);
  }

  // Radix only fires onOpenChange for user gestures; the menu opens the dialog
  // programmatically, so the subject load has to key off the `open` prop itself.
  useEffect(() => {
    if (open && !loaded.current) {
      loaded.current = true;
      void load();
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleOpenChange(next: boolean) {
    if (!next) {
      loaded.current = false;
      setSelected(EMPTY_SELECTION);
      setVersion("latest");
      setMessage(null);
    }
    onOpenChange(next);
  }

  const totalSelected = SUBJECT_KINDS.reduce((count, kind) => count + selected[kind].length, 0);

  async function submit() {
    if (busy || totalSelected === 0) return;
    setBusy(true);
    setMessage(null);
    let saved = 0;
    let failed = 0;
    let lastError = "";
    for (const kind of SUBJECT_KINDS) {
      for (const subjectId of selected[kind]) {
        const result = await corporateMutationAction({
          organizationId: context.organizationId,
          csrfToken: context.csrfToken,
          path: `/v1/corporate/organizations/${context.organizationId}/catalog-assignments`,
          method: "PUT",
          body: {
            schema_version: 1,
            subject_kind: kind,
            subject_id: subjectId,
            object_kind: objectKind,
            stable_id: stableId,
            selector: version === "latest" ? "latest" : "exact",
            version: version === "latest" ? null : version,
            state: "current",
            expected_revision: 0,
            authorization_revision: context.authorizationRevision,
            idempotency_key: crypto.randomUUID(),
          },
        });
        if (result.ok) saved += 1;
        else {
          failed += 1;
          lastError = result.message;
        }
      }
    }
    setBusy(false);
    if (failed === 0) {
      onOpenChange(false);
      router.refresh();
      return;
    }
    setMessage(
      saved > 0
        ? h.assignPartial.replace("{saved}", String(saved)).replace("{failed}", String(failed))
        : lastError || h.assignFailed,
    );
    router.refresh();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{h.dialogTitle}</DialogTitle>
          <DialogDescription>{objectName}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2 text-sm">
            <Label htmlFor="assign-version">{h.version}</Label>
            <select
              id="assign-version"
              className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
              value={version}
              disabled={busy || loading}
              onChange={(event) => {
                setVersion(event.target.value);
              }}
            >
              <option value="latest">{h.latest}</option>
              {versions.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          {SUBJECT_KINDS.map((kind) => (
            <SearchableMultiSelect
              key={kind}
              name={`assign-${kind}`}
              label={h[kind === "technology" ? "technologies" : kind]}
              searchLabel={h.search}
              options={options[kind]}
              selected={selected[kind]}
              onChange={(values) => {
                setSelected((current) => ({ ...current, [kind]: values }));
              }}
              closeLabel={h.closeFilters}
              modal
            />
          ))}
          {loading ? <p className="text-muted-foreground text-sm">{h.loading}</p> : null}
          {message ? <p className="text-destructive text-sm">{message}</p> : null}
        </div>
        <DialogFooter>
          <Button
            disabled={busy || loading || totalSelected === 0}
            onClick={() => {
              void submit();
            }}
          >
            {h.assign}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
