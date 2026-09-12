"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/lib/i18n/navigation";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Icon } from "@/theme";
import type { CorporateTeamView } from "@/lib/api/generated/types.gen";

// eslint-disable-next-line max-lines-per-function
export function CorporateTeamEditor({
  team,
  organizationId,
  authorizationRevision,
  csrfToken,
  canManage,
}: {
  team?: CorporateTeamView;
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  canManage: boolean;
}) {
  const t = useTranslations("corporate");
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(team?.name ?? "");
  const [description, setDescription] = useState(team?.description ?? "");
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  if (!canManage) return null;

  function save(
    state = team?.state ?? "active",
    submittedName = name,
    submittedDescription = description,
  ) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        path: `/v1/corporate/organizations/${organizationId}/teams${team ? `/${team.team_id}` : ""}`,
        method: team ? "PATCH" : "POST",
        body: {
          schema_version: 1,
          name: submittedName,
          description: submittedDescription,
          authorization_revision: authorizationRevision,
          idempotency_key: crypto.randomUUID(),
          ...(team ? { state, expected_revision: team.revision } : {}),
        },
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      setEditing(false);
      if (
        !team &&
        typeof result.data === "object" &&
        result.data !== null &&
        "team_id" in result.data &&
        typeof result.data.team_id === "string"
      ) {
        router.push(`/corporate/teams/${encodeURIComponent(result.data.team_id)}`);
      }
      setMessage(t("saved"));
      router.refresh();
    });
  }
  function beginEdit() {
    setName(team?.name ?? "");
    setDescription(team?.description ?? "");
    setMessage(null);
    setEditing(true);
  }
  return (
    <div className="space-y-4">
      {!editing &&
        (team ? (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button variant="outline" size="icon" aria-label={t("actions")} disabled={busy}>
                <Icon name="more" />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                className="border-border bg-popover text-popover-foreground z-50 min-w-48 rounded-lg border p-1 shadow-md"
              >
                <DropdownMenu.Item
                  onSelect={beginEdit}
                  className="focus:bg-muted flex cursor-default items-center gap-2 rounded-sm px-3 py-2 outline-none"
                >
                  <Icon name="edit" size="sm" />
                  {t("edit")}
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  onSelect={() => {
                    if (team.state === "active" && !window.confirm(t("archiveTeamConfirm"))) return;
                    save(
                      team.state === "active" ? "archived" : "active",
                      team.name,
                      team.description,
                    );
                  }}
                  className="focus:bg-muted cursor-default rounded-sm px-3 py-2 outline-none"
                >
                  {t(team.state === "active" ? "archiveTeam" : "restoreTeam")}
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        ) : (
          <Button onClick={beginEdit}>
            <Icon name="plus" size="sm" />
            {t("createTeam")}
          </Button>
        ))}
      {editing && (
        <form
          className="border-border bg-card space-y-4 rounded-lg border p-5"
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <h2 className="text-xl font-medium">{t(team ? "edit" : "createTeam")}</h2>
          <div className="space-y-2">
            <Label htmlFor="team-name">{t("name")}</Label>
            <Input
              id="team-name"
              required
              maxLength={200}
              value={name}
              disabled={busy}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="team-description">{t("description")}</Label>
            <textarea
              id="team-description"
              rows={3}
              maxLength={2000}
              value={description}
              disabled={busy}
              onChange={(event) => {
                setDescription(event.target.value);
              }}
              aria-describedby="team-description-hint"
              className="border-input bg-background focus-visible:ring-ring w-full rounded-sm border px-3 py-2 text-sm outline-none focus-visible:ring-2"
            />
            <p id="team-description-hint" className="text-muted-foreground text-sm">
              {t("descriptionHint")}
            </p>
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy || !name.trim()}>
              {t(busy ? "saving" : team ? "update" : "createTeam")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setEditing(false);
              }}
            >
              {t("cancel")}
            </Button>
          </div>
        </form>
      )}
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
    </div>
  );
}
