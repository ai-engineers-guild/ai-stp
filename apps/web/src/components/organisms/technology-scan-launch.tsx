"use client";

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import { corporateMutationAction } from "@/actions/corporate";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/atoms/dialog";
import { useRouter } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
import type {
  CorporateProjectView,
  TechnologyScanLaunchResult,
} from "@/lib/api/generated/types.gen";

// eslint-disable-next-line max-lines-per-function
export function TechnologyScanLaunch({
  organizationId,
  authorizationRevision,
  csrfToken,
  projects,
  activeProjectIds = [],
  variant = "default",
  size,
  label,
}: {
  organizationId: string;
  authorizationRevision: string | number;
  csrfToken: string;
  projects: CorporateProjectView[];
  activeProjectIds?: string[];
  variant?: "default" | "outline";
  size?: "lg" | undefined;
  label?: string;
}) {
  const t = useTranslations("technology");
  const scans = useTranslations("technology.scans");
  const router = useRouter();
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const [launched, setLaunched] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<TechnologyScanLaunchResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const names = new Map(projects.map((project) => [project.project_id, project.name]));

  function launch() {
    const effect = JSON.stringify([...selected].sort());
    if (retry.current?.effect !== effect) retry.current = { effect, key: crypto.randomUUID() };
    const body = {
      schema_version: 1,
      expected_revision: 0,
      authorization_revision: authorizationRevision,
      idempotency_key: retry.current.key,
      project_ids: selected,
    };
    setMessage(null);
    startTransition(async () => {
      const response = await corporateMutationAction({
        csrfToken,
        organizationId,
        path: `/v1/corporate/organizations/${organizationId}/technology-scans`,
        method: "POST",
        body,
      });
      if (!response.ok) {
        setMessage(response.message);
        return;
      }
      retry.current = null;
      const launchResult = response.data as TechnologyScanLaunchResult;
      setResult(launchResult);
      const queued = launchResult.items
        .filter((item) => item.state === "queued")
        .map((item) => item.project_id);
      setLaunched((current) => [...current, ...queued]);
      setSelected([]);
      router.refresh();
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setSelected([]);
          setResult(null);
          setMessage(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant={variant} size={size}>
          <Icon name="play" size="sm" />
          {label ?? scans("launch")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{scans("launchTitle")}</DialogTitle>
          <DialogDescription>{scans("launchDescription")}</DialogDescription>
        </DialogHeader>
        <fieldset disabled={busy} className="max-h-80 space-y-1 overflow-y-auto">
          <legend className="sr-only">{scans("launchProjects")}</legend>
          {projects.map((project) => {
            const repository = project.repositories?.[0];
            const repositoryUrl = repository?.repository_url;
            const active =
              activeProjectIds.includes(project.project_id) ||
              launched.includes(project.project_id);
            const linked = Boolean(repositoryUrl) && !active;
            return (
              <div key={project.project_id} className="flex min-h-11 items-start gap-3 py-1">
                <input
                  id={`scan-project-${project.project_id}`}
                  type="checkbox"
                  className="accent-primary mt-1 h-4 w-4"
                  disabled={!linked}
                  checked={selected.includes(project.project_id)}
                  onChange={(event) => {
                    setSelected((value) =>
                      event.target.checked
                        ? [...value, project.project_id]
                        : value.filter((id) => id !== project.project_id),
                    );
                  }}
                />
                <Label htmlFor={`scan-project-${project.project_id}`} className="min-w-0">
                  <span className="block font-medium">{project.name}</span>
                  <span className="text-muted-foreground block font-mono text-xs break-all">
                    {repositoryUrl
                      ? `${repositoryUrl}${repository.default_branch ? ` · ${repository.default_branch}` : ""}`
                      : scans("launchNoRepository")}
                  </span>
                  {active && (
                    <span className="text-warning block text-sm">{scans("launchActive")}</span>
                  )}
                </Label>
              </div>
            );
          })}
          {!projects.length && (
            <p className="text-muted-foreground text-sm">{scans("launchEmpty")}</p>
          )}
        </fieldset>
        <div className="flex flex-wrap gap-3">
          <Button size="lg" disabled={busy || Boolean(result) || !selected.length} onClick={launch}>
            {busy ? t("saving") : scans("launchStart", { count: selected.length })}
          </Button>
        </div>
        {message && (
          <p role="status" className="text-sm">
            {message}
          </p>
        )}
        {result && (
          <ul className="divide-border divide-y text-sm" aria-label={scans("launchResults")}>
            {result.items.map((item) => (
              <li
                key={item.project_id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2"
              >
                <span className="font-medium">{names.get(item.project_id) ?? item.project_id}</span>
                <Badge variant={item.state === "queued" ? "secondary" : "warning"}>
                  {scans(`launchState.${item.state}`)}
                </Badge>
                {item.detail && (
                  <span className="text-muted-foreground text-xs">{item.detail}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
