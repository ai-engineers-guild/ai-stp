import { getTranslations } from "next-intl/server";

import {
  listOwnerObjects,
  readOwnerExternalProducts,
  readOwnerObject,
  readOwnerPresentation,
  readOwnerVersion,
} from "@/lib/api/owner";
import { listStaffReports, readStaffReport } from "@/lib/api/reports";
import { readPublicationPlan } from "@/lib/api/publications";
import { sessionCookieValue } from "@/lib/auth/require-session";
import {
  invitationPublicFacts,
  ownerObjectPublicFacts,
  ownerVersionPublicFacts,
  publicationPublicFacts,
  staffCasePublicFacts,
} from "@/lib/projection/page-facts";
import { orNotFound } from "@/lib/projection/not-found";
import { presentOwnerObjects, presentReportCases } from "@/lib/projection/private-presenters";
import {
  presentInvitation,
  presentOwnerObjectDetail,
  presentOwnerVersion,
  presentPresentationEdit,
  presentPublication,
  presentStaffCase,
} from "@/lib/projection/workspace-presenters";
import type { MachineRoute } from "@/lib/projection/route-table";

export const WORKSPACE_ROUTES: MachineRoute[] = [
  {
    pattern: "objects",
    resolve: async () => {
      const t = await getTranslations("objects");
      const tc = await getTranslations("common");
      const tm = await getTranslations("machineDoc");
      const list = await listOwnerObjects((await sessionCookieValue()) ?? "");
      return presentOwnerObjects({
        title: t("title"),
        subtitle: t("subtitle"),
        emptyMessage: t("empty"),
        items: list.items.map((item) => ({
          name: item.name,
          stableId: item.stable_id,
          objectKind: item.object_kind,
          latestVersion: item.latest_version,
          lifecycle: item.lifecycle_state,
          authorVerified: item.author_verified,
          componentVerified: item.component_verified,
          updatedAt: item.updated_at,
        })),
        labels: {
          yes: tc("yes"),
          no: tc("no"),
          stableId: tm("stableId"),
          objectKind: tm("objectKind"),
          version: tm("version"),
          lifecycle: tm("lifecycle"),
          authorVerified: tm("authorVerified"),
          componentVerified: tm("componentVerified"),
          updatedAt: tm("updatedAt"),
        },
      });
    },
  },
  {
    pattern: "objects/component/:stableId/edit",
    resolve: async ({ segments }) => {
      const stableId = segments[2] ?? "";
      const t = await getTranslations("objects");
      const tm = await getTranslations("machineDoc");
      const presentation = await orNotFound(
        readOwnerPresentation((await sessionCookieValue()) ?? "", stableId),
      );
      if (!presentation) return null;
      return presentPresentationEdit({
        title: t("editPresentation"),
        note: t("editPresentationNote"),
        stableId,
        bio: presentation.bio,
        labels: { stableId: tm("stableId"), bio: tm("bio") },
      });
    },
  },
  {
    pattern: "objects/:kind/:stableId/versions/:version",
    resolve: async ({ segments }) => {
      const kind = segments[1] ?? "";
      const stableId = segments[2] ?? "";
      const version = segments[4] ?? "";
      if (kind !== "component" && kind !== "setup") return null;
      const tc = await getTranslations("common");
      const tm = await getTranslations("machineDoc");
      const detail = await orNotFound(
        readOwnerVersion((await sessionCookieValue()) ?? "", kind, stableId, version),
      );
      if (!detail) return null;
      return presentOwnerVersion({
        ...ownerVersionPublicFacts(detail),
        labels: {
          yes: tc("yes"),
          no: tc("no"),
          objectKind: tm("objectKind"),
          stableId: tm("stableId"),
          version: tm("version"),
          lifecycle: tm("lifecycle"),
          visibility: tm("visibility"),
          digest: tm("digest"),
          authorVerified: tm("authorVerified"),
          componentVerified: tm("componentVerified"),
          installEligible: tm("installEligible"),
        },
      });
    },
  },
  {
    pattern: "objects/:kind/:stableId",
    resolve: async ({ segments }) => {
      const kind = segments[1] ?? "";
      const stableId = segments[2] ?? "";
      if (kind !== "component" && kind !== "setup") return null;
      const t = await getTranslations("objects");
      const tm = await getTranslations("machineDoc");
      const token = (await sessionCookieValue()) ?? "";
      const detail = await orNotFound(readOwnerObject(token, kind, stableId));
      if (!detail) return null;
      const attached =
        process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED === "false"
          ? { items: [] as Array<{ canonical_domain: string }> }
          : await readOwnerExternalProducts(token, kind, stableId).catch(() => ({ items: [] }));
      const facts = ownerObjectPublicFacts({
        ...detail,
        attachedDomains: attached.items.map((item) => item.canonical_domain),
      });
      return presentOwnerObjectDetail({
        ...facts,
        labels: {
          objectKind: tm("objectKind"),
          stableId: tm("stableId"),
          version: tm("version"),
          digest: tm("digest"),
          viewPublic: t("viewPublic"),
          editPresentation: t("editPresentation"),
          versions: t("versions"),
          emptyVersions: t("noVersions"),
          services: tm("services"),
        },
      });
    },
  },
  {
    pattern: "publications/:planId",
    resolve: async ({ segments }) => {
      const planId = segments[1] ?? "";
      const t = await getTranslations("publications");
      const tm = await getTranslations("machineDoc");
      const plan = await orNotFound(
        readPublicationPlan((await sessionCookieValue()) ?? "", planId),
      );
      if (!plan) return null;
      return presentPublication({
        title: t("title"),
        subtitle: t("subtitle"),
        ...publicationPublicFacts(plan),
        labels: {
          planId: tm("planId"),
          state: tm("state"),
          objectKind: tm("objectKind"),
          stableId: tm("stableId"),
          version: tm("version"),
          digest: tm("digest"),
          planHash: tm("planHash"),
          policy: tm("policy"),
          expires: tm("expires"),
          effects: tm("effects"),
        },
      });
    },
  },
  {
    pattern: "invitations/:invitationId",
    resolve: async ({ segments }) => {
      const t = await getTranslations("invitations");
      const tm = await getTranslations("machineDoc");
      const facts = invitationPublicFacts(segments[1] ?? "");
      return presentInvitation({
        title: t("title"),
        subtitle: t("subtitle"),
        invitationId: facts.invitationId,
        labels: { invitationId: tm("invitationId") },
      });
    },
  },
  {
    pattern: "staff/reports",
    resolve: async () => {
      const t = await getTranslations("staff");
      const tc = await getTranslations("common");
      const tm = await getTranslations("machineDoc");
      const cases = await listStaffReports((await sessionCookieValue()) ?? "");
      return presentReportCases({
        title: t("title"),
        subtitle: t("subtitle"),
        emptyMessage: t("empty"),
        detailHref: (caseId) => "/staff/reports/" + caseId,
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
    pattern: "staff/reports/:caseId",
    resolve: async ({ segments }) => {
      const t = await getTranslations("staff");
      const tc = await getTranslations("common");
      const tm = await getTranslations("machineDoc");
      const detail = await orNotFound(
        readStaffReport((await sessionCookieValue()) ?? "", segments[2] ?? ""),
      );
      if (!detail) return null;
      return presentStaffCase({
        title: t("caseDetail"),
        ...staffCasePublicFacts(detail),
        labels: {
          yes: tc("yes"),
          no: tc("no"),
          caseId: tm("caseId"),
          state: tm("state"),
          vulnerability: tm("vulnerability"),
          objectKind: tm("objectKind"),
          stableId: tm("stableId"),
          version: tm("version"),
          digest: tm("digest"),
          errorCode: tm("errorCode"),
          harness: tm("harness"),
        },
      });
    },
  },
];
