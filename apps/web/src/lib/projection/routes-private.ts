import { getTranslations } from "next-intl/server";

import { listDevices } from "@/lib/api/devices";
import {
  readCorporateWorkspace,
  readCorporateOverview,
  readCorporateDirectory,
  readCorporateResource,
} from "@/lib/api/corporate";
import { readProjectTechnologyDetail } from "@/lib/api/technology";
import { listGrants } from "@/lib/api/grants";
import { listOwnReports, readOwnReport } from "@/lib/api/reports";
import { listCatalogReactions } from "@/lib/api/reactions";
import { privacyFieldsFromAccount, readAccount } from "@/lib/api/account";
import { previewOwnerPublicProfile, readOwnerPublicProfile } from "@/lib/api/public-profile";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { accountPrivacyPublicFacts, accountProfilePublicFacts } from "@/lib/projection/page-facts";
import { orNotFound } from "@/lib/projection/not-found";
import {
  presentAccess,
  presentAccount,
  presentDevices,
  presentReportCases,
} from "@/lib/projection/private-presenters";
import {
  presentAccountPreview,
  presentAccountPrivacy,
  presentAccountProfile,
} from "@/lib/projection/workspace-presenters";
import { WORKSPACE_ROUTES } from "@/lib/projection/routes-workspace";
import type { MachineRoute } from "@/lib/projection/route-table";
import { presentPage } from "@/lib/projection/presenters";
import { corporateNodeHref } from "@/lib/corporate-overview";
import { TECHNOLOGY_ROUTES } from "@/lib/projection/routes-technology";
import { CORPORATE_ROUTES } from "@/lib/projection/routes-corporate";

/**
 * Machine documents for the account, owner and staff sections. Access is
 * unchanged by the projection: these routes sit behind the same session gate
 * as their human twins (SPEC-036, REQ-3611).
 */

const ACCOUNT_ROUTES: MachineRoute[] = [
  ...TECHNOLOGY_ROUTES,
  ...CORPORATE_ROUTES,
  {
    pattern: "onboarding",
    resolve: async () => {
      const t = await getTranslations("onboarding");
      return presentPage({ title: t("title"), summary: t("body") });
    },
  },
  {
    pattern: "account",
    resolve: async () => {
      const t = await getTranslations("account");
      const tm = await getTranslations("machineDoc");
      const profile = await readAccount((await sessionCookieValue()) ?? "");
      return presentAccount({
        title: t("title"),
        accountId: profile.account_id,
        identities: profile.identities.map((identity) => ({
          provider: identity.provider,
          displayName: identity.display_name,
          linkedAt: identity.linked_at,
        })),
        labels: {
          accountId: tm("accountId"),
          signInMethods: tm("signInMethods"),
          provider: tm("provider"),
          linkedAt: tm("linkedAt"),
          displayName: tm("displayName"),
        },
        links: [
          [t("editProfile"), "/account/profile"],
          [t("privacy"), "/account/privacy"],
          [t("viewPublicProfile"), "/account/profile/preview"],
        ],
      });
    },
  },
  {
    pattern: "account/github",
    resolve: async () => {
      const t = await getTranslations("githubConnector");
      return presentPage({
        title: t("title"),
        summary: t("simpleIntro"),
        links: [[t("back"), "/account"]],
      });
    },
  },
  {
    pattern: "account/privacy",
    resolve: async () => {
      const t = await getTranslations("account");
      const tc = await getTranslations("common");
      const tm = await getTranslations("machineDoc");
      const profile = await readAccount((await sessionCookieValue()) ?? "");
      const privacy = accountPrivacyPublicFacts(privacyFieldsFromAccount(profile));
      return presentAccountPrivacy({
        title: t("privacy"),
        subtitle: t("privacySubtitle"),
        ...privacy,
        labels: {
          yes: tc("yes"),
          no: tc("no"),
          showProfilePublicly: tm("showProfilePublicly"),
          allowPublisherListing: tm("allowPublisherListing"),
        },
      });
    },
  },
  {
    pattern: "account/profile",
    resolve: async () => {
      const t = await getTranslations("account");
      const tm = await getTranslations("machineDoc");
      const profile = await readOwnerPublicProfile((await sessionCookieValue()) ?? "");
      const facts = accountProfilePublicFacts(profile.editable.fields);
      return presentAccountProfile({
        title: t("profile"),
        subtitle: t("profileSubtitle"),
        ...facts,
        labels: { displayName: tm("displayName"), bio: tm("bio") },
      });
    },
  },
  {
    pattern: "account/profile/preview",
    resolve: async () => {
      const t = await getTranslations("account");
      const preview = await orNotFound(
        previewOwnerPublicProfile((await sessionCookieValue()) ?? ""),
      );
      if (!preview) {
        return presentAccountPreview({
          title: t("profile"),
          banner: t("profilePreviewEmpty"),
          displayName: null,
          bio: null,
          links: [],
        });
      }
      const projection = preview.projection;
      return presentAccountPreview({
        title: t("viewPublicProfile"),
        banner: t("profilePreviewBanner"),
        displayName: projection.display_name,
        bio: projection.bio,
        links: projection.links.map((item) => ({ label: item.label, url: item.url })),
      });
    },
  },
  ...["corporate", "corporate/overview"].map((pattern): MachineRoute => ({
    pattern,
    resolve: async () => {
      const t = await getTranslations("corporate");
      const graph = await readCorporateOverview((await sessionCookieValue()) ?? "");
      if (!graph) return presentPage({ title: t("emptyTitle"), summary: t("emptyBody") });
      const h = await getTranslations("hub");
      return presentPage({
        title: graph.organization.display_name,
        summary: t("subtitle"),
        links: graph.nodes.map((node) => [node.name, corporateNodeHref(node)] as const),
        fields: graph.nodes.flatMap((node) => {
          const children = graph.edges
            .filter((edge) => edge.parent_id === node.id)
            .map((edge) => graph.nodes.find((child) => child.id === edge.child_id)?.name)
            .filter(Boolean)
            .join(", ");
          const assignments = node.assignments
            .map((item) => `${item.display_name || h(item.object_kind)} ${item.version}`)
            .join(", ");
          return [
            [node.name, children || "-"],
            [
              `${node.name}: ${h("catalogAssignments")}`,
              node.assignments_readable
                ? assignments || h("noAssignments")
                : h("assignmentsRestricted"),
            ],
          ] as const;
        }),
      });
    },
  })),
  {
    pattern: "corporate/dashboard",
    resolve: async () => presentPage({ title: (await getTranslations("hub"))("dashboard") }),
  },
  {
    pattern: "corporate/organization/admins",
    resolve: async () => {
      const t = await getTranslations("hub");
      const workspace = await readCorporateWorkspace((await sessionCookieValue()) ?? "");
      return presentPage({
        title: t("admins"),
        fields:
          workspace?.roles?.items.map((role) => [role.name, role.permissions.join(", ")]) ?? [],
        links: [[t("organization"), "/corporate/organization"]],
      });
    },
  },
  {
    pattern: "corporate/:resource",
    resolve: async ({ segments }) => {
      const resource = segments[1];
      if (resource !== "projects" && resource !== "teams" && resource !== "members") return null;
      const t = await getTranslations("hub");
      const directory = await readCorporateDirectory((await sessionCookieValue()) ?? "", resource);
      return presentPage({
        title: t(resource === "members" ? "employees" : resource),
        links:
          directory?.items.map((item) => [
            item.name,
            `/corporate/${resource}/${encodeURIComponent(item.id)}`,
          ]) ?? [],
      });
    },
  },
  {
    pattern: "corporate/:resource/:resourceId",
    resolve: async ({ segments }) => {
      const t = await getTranslations("corporate");
      const resource = segments[1];
      const resourceId = segments[2];
      if (
        !resourceId ||
        (resource !== "projects" &&
          resource !== "teams" &&
          resource !== "members" &&
          resource !== "roles")
      )
        return null;
      const workspace = await readCorporateResource(
        (await sessionCookieValue()) ?? "",
        resource,
        resourceId,
      );
      if (!workspace) return presentPage({ title: t("emptyTitle"), summary: t("emptyBody") });
      const projectDetail =
        resource === "projects" && resourceId
          ? await readProjectTechnologyDetail(
              (await sessionCookieValue()) ?? "",
              workspace.organization.organization_id,
              resourceId,
            )
          : null;
      const project = projectDetail?.project;
      const team = workspace.team;
      const member = workspace.member;
      if (resource === "projects" && project) {
        const technologyLabels = await getTranslations("technology");
        return presentPage({
          title: project.name,
          summary: t("projectDetailsBody"),
          fields: [[t("state"), project.lifecycle ?? project.state]],
          sections: (projectDetail.relations?.items ?? [])
            .filter((usage) => usage.state === "current")
            .map((usage) => ({
              heading:
                projectDetail.technologies.find(
                  (item) => item.technology_id === usage.technology_id,
                )?.name ?? technologyLabels("values.unknown"),
              entries: usage.facts.map((fact) => ({
                title: technologyLabels(`values.${fact.context}`),
                href: `/corporate/technologies/${usage.technology_id}`,
                fields: [[technologyLabels("version"), fact.version ?? "unknown"]],
              })),
            })),
          links: [[t("backToWorkspace"), "/corporate/projects"]],
        });
      }
      if (resource === "teams" && team) {
        return presentPage({
          title: team.name,
          summary: t("teamDetailsBody"),
          fields: [[t("state"), team.state]],
          links: [[t("backToWorkspace"), "/corporate/teams"]],
        });
      }
      if (resource === "members" && member) {
        return presentPage({
          title: member.display_name ?? t("member"),
          summary: t("memberDetailsBody"),
          fields: [[t("state"), member.state]],
          links: [[t("backToWorkspace"), "/corporate/members"]],
        });
      }
      if (resource === "roles" && workspace.role)
        return presentPage({
          title: workspace.role.name,
          fields: [[t("permissions"), workspace.role.permissions.join(", ")]],
          links: [[t("backToWorkspace"), "/corporate/organization/admins"]],
        });
      return null;
    },
  },
  {
    pattern: "devices",
    resolve: async () => {
      const t = await getTranslations("devices");
      const tc = await getTranslations("common");
      const tm = await getTranslations("machineDoc");
      const devices = await listDevices((await sessionCookieValue()) ?? "");
      return presentDevices({
        title: t("title"),
        subtitle: t("subtitle"),
        emptyMessage: t("empty"),
        devices: devices.items.map((device) => ({
          deviceId: device.device_id,
          deviceType: device.device_type,
          state: device.state,
          lastActiveAt: device.last_active_at,
          location: device.approximate_location,
          current: false,
        })),
        labels: {
          yes: tc("yes"),
          no: tc("no"),
          deviceType: tm("deviceType"),
          state: tm("state"),
          lastConnected: tm("lastActiveAt"),
          approximateLocation: tm("location"),
          locationUnknown: tm("unknown"),
          current: tm("currentDevice"),
        },
      });
    },
  },
  {
    pattern: "access",
    resolve: async () => {
      const t = await getTranslations("access");
      const tm = await getTranslations("machineDoc");
      const grants = await listGrants((await sessionCookieValue()) ?? "");
      return presentAccess({
        title: t("title"),
        subtitle: t("subtitle"),
        invitations: grants.invitations.map((item) => ({
          invitationId: item.invitation_id,
          objectKind: item.object_kind,
          stableId: item.stable_id,
          major: item.major,
          state: item.state,
          expiresAt: item.expires_at,
        })),
        grants: grants.grants.map((item) => ({
          grantId: item.grant_id,
          objectKind: item.object_kind,
          stableId: item.stable_id,
          major: item.major,
          grantee: item.grantee_account_id,
          revokedAt: item.revoked_at,
        })),
        labels: {
          invitations: t("invitations"),
          grants: t("grants"),
          emptyInvitations: t("emptyInvitations"),
          emptyGrants: t("emptyGrants"),
          stableId: tm("stableId"),
          kind: tm("objectKind"),
          major: tm("major"),
          state: tm("state"),
          expires: tm("expiresAt"),
          grantee: tm("grantee"),
          revoked: tm("revokedAt"),
        },
      });
    },
  },
  {
    pattern: "likes",
    resolve: async () => {
      const t = await getTranslations("myLikes");
      const reactions = await listCatalogReactions((await sessionCookieValue()) ?? "");
      return presentPage({
        title: t("title"),
        summary: t("subtitle"),
        fields: reactions.items.map((item) => [item.object_kind, item.summary.stable_id]),
        links: reactions.items.map((item) => [
          item.summary.latest_name,
          `/catalog/${item.object_kind === "component" ? "components" : "setups"}/${item.summary.stable_id}`,
        ]),
      });
    },
  },
  {
    pattern: "reports",
    resolve: async () => {
      const t = await getTranslations("reports");
      const tc = await getTranslations("common");
      const tm = await getTranslations("machineDoc");
      const cases = await listOwnReports((await sessionCookieValue()) ?? "");
      return presentReportCases({
        title: t("title"),
        subtitle: t("subtitle"),
        emptyMessage: t("empty"),
        cases: cases.items.map((item) => ({
          caseId: item.case_id,
          objectKind: item.object_kind,
          stableId: item.stable_id,
          version: item.version,
          state: item.state,
          vulnerability: item.vulnerability,
          createdAt: item.created_at,
        })),
        labels: {
          yes: tc("yes"),
          no: tc("no"),
          objectKind: tm("objectKind"),
          stableId: tm("stableId"),
          version: tm("version"),
          state: tm("state"),
          vulnerability: tm("vulnerability"),
          createdAt: tm("createdAt"),
        },
      });
    },
  },
  {
    pattern: "reports/:caseId",
    resolve: async ({ segments }) => {
      const t = await getTranslations("reports");
      const tm = await getTranslations("machineDoc");
      const detail = await orNotFound(
        readOwnReport((await sessionCookieValue()) ?? "", segments[1] ?? ""),
      );
      if (!detail) return null;
      return presentPage({
        title: t("caseDetails"),
        fields: [
          [tm("caseId"), detail.case_id],
          [tm("state"), detail.state],
          [tm("objectKind"), detail.object_kind || "-"],
          [tm("stableId"), detail.stable_id || "-"],
          [tm("version"), detail.version || "-"],
          [tm("vulnerability"), detail.vulnerability ? "true" : "false"],
          [tm("createdAt"), detail.created_at],
        ],
        links: [["Reports", "/reports"]],
      });
    },
  },
];

export const PRIVATE_ROUTES: MachineRoute[] = [...ACCOUNT_ROUTES, ...WORKSPACE_ROUTES];
