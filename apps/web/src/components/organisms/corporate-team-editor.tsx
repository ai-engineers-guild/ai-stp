"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/lib/i18n/navigation";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { EntityEditorField, EntityEditorLayout } from "@/components/molecules/entity-editor-layout";
import { MarkdownEditor } from "@/components/molecules/markdown-editor";
import { ENTITY_EDITOR_CONFIGS } from "@/lib/entity-editor-contract";
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
  const [descriptionMode, setDescriptionMode] = useState<"write" | "preview">("write");
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
    setDescriptionMode("write");
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
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <EntityEditorLayout
            config={ENTITY_EDITOR_CONFIGS.team}
            title={t(team ? "edit" : "createTeam")}
            description={t("descriptionHint")}
            blocks={{
              displayName: (
                <EntityEditorField label={t("name")} htmlFor="team-name" required>
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
                </EntityEditorField>
              ),
              description: (
                <MarkdownEditor
                  id="team-description"
                  label={t("description")}
                  value={description}
                  mode={descriptionMode}
                  onChange={setDescription}
                  onModeChange={setDescriptionMode}
                  maxLength={2000}
                  labels={{ write: t("markdownWrite"), preview: t("markdownPreview") }}
                />
              ),
            }}
            afterBlocks={
              <div className="flex flex-col-reverse gap-2 sm:flex-row">
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
                <Button type="submit" disabled={busy || !name.trim()}>
                  {t(busy ? "saving" : team ? "update" : "createTeam")}
                </Button>
              </div>
            }
          />
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
