import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessWorkspace } from "@/components/organisms/access-workspace";
import type { AccessGrantResponse } from "@/lib/api/generated/types.gen";
import type { AccessUser } from "@/components/organisms/access-workspace";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { listGrants } from "@/lib/api/grants";
import { loadEntityActionMenus } from "@/actions/entity-actions";
import { listOwnerObjects } from "@/lib/api/owner";
import { loadPublisherProfiles } from "@/lib/catalog-load";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ object_kind?: string; stable_id?: string }>;
};

export default async function AccessPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const sp = await searchParams;
  setRequestLocale(locale);
  const session = await requireSession(locale, `/${locale}/access`);
  const t = await getTranslations("access");
  const tc = await getTranslations("common");
  const token = await sessionCookieValue();
  const csrf = await readCsrfToken();
  const objectKind =
    sp.object_kind === "setup" || sp.object_kind === "component" ? sp.object_kind : undefined;
  const stableId = sp.stable_id?.trim() || undefined;

  let grants;
  try {
    grants = await listGrants(token ?? "");
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  const canCreate = await mayCreateGrant(objectKind, stableId);

  let objectName: string | null = null;
  let objectVersion: string | null = null;
  if (objectKind && stableId) {
    try {
      const ownedObjects = await listOwnerObjects(token ?? "", { page_size: 100 });
      const object = ownedObjects.items.find(
        (item) => item.object_kind === objectKind && item.stable_id === stableId,
      );
      objectName = object?.name ?? null;
      objectVersion = object?.latest_version ?? null;
    } catch {
      // The stable id remains a useful fallback when the owner projection is unavailable.
    }
  }

  const scopedGrants = grants.grants.filter(
    (item) =>
      item.state === "active" &&
      (!objectKind || item.object_kind === objectKind) &&
      (!stableId || item.stable_id === stableId),
  );
  const incoming = scopedGrants.filter(
    (item) =>
      item.grantee_account_id === session.accountId && item.owner_account_id !== session.accountId,
  );
  const outgoing = scopedGrants.filter((item) => item.owner_account_id === session.accountId);
  const profiles = await loadPublisherProfiles([
    ...outgoing.map((item) => item.grantee_account_id),
    ...incoming.map((item) => item.owner_account_id),
  ]);
  const users = outgoing.map((item) => grantUser(item, profiles, false));
  const incomingUsers = incoming.map((item) => grantUser(item, profiles, true));

  if (!csrf) {
    return <StatePanel kind="error" title={tc("sessionExpired")} description={tc("login")} />;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("subtitle")}</p>
      </div>
      {objectKind && stableId ? (
        <Link
          href={`/catalog/${objectKind === "component" ? "components" : "setups"}/${stableId}`}
          className="border-border bg-muted/20 hover:bg-muted/40 focus-visible:ring-ring block max-w-xl rounded-lg border p-4 focus-visible:ring-2 focus-visible:outline-none"
        >
          <p className="font-medium">{objectName ?? stableId}</p>
          <p className="text-muted-foreground mt-1 font-mono text-xs break-all">
            {objectKind} · {stableId}
          </p>
        </Link>
      ) : null}
      <AccessWorkspace
        canCreate={canCreate}
        users={users}
        incomingUsers={incomingUsers}
        incomingLabel={t("receivedAccess")}
        csrfToken={csrf}
        labels={{
          create: t("createInvitation"),
          email: t("email"),
          stableId: t("stableId"),
          kind: t("kind"),
          recipientKind: t("recipientKind"),
          githubUsername: t("githubUsername"),
          userId: t("userId"),
          kindComponent: t("kindComponent"),
          kindSetup: t("kindSetup"),
          peopleWithAccess: t("peopleWithAccess"),
          emptyPeople: t("emptyPeople"),
          revoke: t("revoke"),
          revokeTitle: t("revokeTitle"),
          revokeWarning: t("revokeWarning"),
          cancel: t("cancel"),
          confirm: t("confirm"),
          revoking: t("revoking"),
          copyId: t("copyId"),
          copied: tc("copied"),
          report: t("reportUser"),
          more: t("more"),
          user: t("user"),
          referenceId: tc("referenceId"),
          githubNote: t("githubNote"),
        }}
        initialObjectKind={objectKind}
        initialStableId={stableId}
        initialMajor={Number.parseInt(objectVersion?.split(".")[0] ?? "", 10) || 1}
      />
    </div>
  );
}

async function mayCreateGrant(kind: "component" | "setup" | undefined, id: string | undefined) {
  if (!kind || !id) return true;
  const { menus } = await loadEntityActionMenus([{ kind, id }]);
  return menus.items[0]?.actions.some((action) => action.id === "manage_access") ?? false;
}
function grantUser(
  item: AccessGrantResponse,
  profiles: Awaited<ReturnType<typeof loadPublisherProfiles>>,
  received: boolean,
): AccessUser {
  const accountId = received ? item.owner_account_id : item.grantee_account_id;
  return {
    grantId: item.grant_id,
    objectKind: item.object_kind,
    stableId: item.stable_id,
    major: item.major,
    accountId,
    displayName: profiles[accountId]?.displayName ?? null,
    avatarUrl: profiles[accountId]?.avatarUrl ?? null,
  };
}
