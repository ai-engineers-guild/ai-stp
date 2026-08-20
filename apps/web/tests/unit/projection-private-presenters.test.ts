import { describe, expect, it } from "vitest";

import { machineDocumentToText } from "@/lib/projection/document-text";
import {
  presentAccess,
  presentAccount,
  presentDevices,
  presentOwnerObjects,
  presentReportCases,
} from "@/lib/projection/private-presenters";
import {
  presentAccountPrivacy,
  presentInvitation,
  presentOwnerObjectDetail,
  presentOwnerVersion,
  presentPresentationEdit,
  presentPublication,
  presentStaffCase,
} from "@/lib/projection/workspace-presenters";
import { machineTextLeaks } from "@/lib/projection/page-facts";

const BOOL = { yes: "Yes", no: "No" };

describe("private machine documents (REQ-3611, REQ-3612)", () => {
  it("lists sign-in methods on the account document", () => {
    const text = machineDocumentToText(
      presentAccount({
        title: "Account",
        accountId: "account_01H",
        identities: [
          { provider: "github", displayName: "octocat", linkedAt: "2026-01-02" },
          { provider: "google", displayName: null, linkedAt: "2026-03-04" },
        ],
        labels: {
          accountId: "account_id",
          signInMethods: "Sign-in methods",
          provider: "provider",
          linkedAt: "linked_at",
          displayName: "display_name",
        },
        links: [["Edit profile", "/account/profile"]],
      }),
      "en",
    );

    expect(text).toContain("account_id: account_01H");
    expect(text).toContain("provider: github");
    expect(text).toContain("display_name: octocat");
    expect(text).toContain("linked_at: 2026-03-04");
    expect(text).toContain("[Edit profile](/en/ai/account/profile)");
  });

  it("describes each device with type, state and last activity", () => {
    const text = machineDocumentToText(
      presentDevices({
        title: "Devices",
        subtitle: "Sessions and CLI devices",
        emptyMessage: "No devices",
        devices: [
          {
            deviceId: "device_01H",
            deviceType: "cli",
            state: "active",
            lastActiveAt: "2026-08-01",
            location: null,
            current: true,
          },
        ],
        labels: {
          ...BOOL,
          deviceType: "device_type",
          state: "state",
          lastConnected: "last_active_at",
          approximateLocation: "location",
          locationUnknown: "unknown",
          current: "current",
        },
      }),
      "en",
    );

    expect(text).toContain("device_01H");
    expect(text).toContain("device_type: cli");
    expect(text).toContain("state: active");
    expect(text).toContain("location: unknown");
    expect(text).toContain("current: Yes");
  });

  it("keeps owner objects linkable with their trust flags", () => {
    const text = machineDocumentToText(
      presentOwnerObjects({
        title: "Your objects",
        subtitle: "Owned components and setups",
        emptyMessage: "Nothing yet",
        items: [
          {
            name: "ai-repo-safety",
            stableId: "component_01H",
            objectKind: "component",
            latestVersion: "0.1",
            lifecycle: "published",
            authorVerified: false,
            componentVerified: true,
            updatedAt: "2026-08-02",
          },
        ],
        labels: {
          ...BOOL,
          stableId: "stable_id",
          objectKind: "object_kind",
          version: "version",
          lifecycle: "lifecycle",
          authorVerified: "author_verified",
          componentVerified: "component_verified",
          updatedAt: "updated_at",
        },
      }),
      "en",
    );

    expect(text).toContain("[ai-repo-safety](/en/ai/objects/component/component_01H)");
    expect(text).toContain("stable_id: component_01H");
    expect(text).toContain("version: 0.1");
    expect(text).toContain("author_verified: No");
    expect(text).toContain("component_verified: Yes");
  });

  it("separates invitations from grants and reports empty sections", () => {
    const text = machineDocumentToText(
      presentAccess({
        title: "Access",
        subtitle: "Invitations and grants",
        invitations: [
          {
            invitationId: "invitation_01H",
            objectKind: "setup",
            stableId: "setup_01H",
            major: 1,
            state: "pending",
            expiresAt: "2026-09-01",
          },
        ],
        grants: [],
        labels: {
          invitations: "Invitations",
          grants: "Grants",
          emptyInvitations: "No invitations",
          emptyGrants: "No grants",
          stableId: "stable_id",
          kind: "object_kind",
          major: "major",
          state: "state",
          expires: "expires_at",
          grantee: "grantee",
          revoked: "revoked_at",
        },
      }),
      "en",
    );

    expect(text).toContain("## Invitations");
    expect(text).toContain("[invitation_01H](/en/ai/invitations/invitation_01H)");
    expect(text).toContain("major: 1");
    expect(text).toContain("## Grants");
    expect(text).toContain("No grants");
  });

  it("marks vulnerability on report cases and links staff detail", () => {
    const doc = presentReportCases({
      title: "Reports",
      subtitle: "Cases you filed",
      emptyMessage: "No cases",
      detailHref: (caseId) => `/staff/reports/${caseId}`,
      cases: [
        {
          caseId: "case_01H",
          objectKind: "component",
          stableId: "component_01H",
          version: "1.0",
          state: "triaged",
          vulnerability: true,
          createdAt: "2026-08-03",
        },
      ],
      labels: {
        ...BOOL,
        objectKind: "object_kind",
        stableId: "stable_id",
        version: "version",
        state: "state",
        vulnerability: "vulnerability",
        createdAt: "created_at",
      },
    });
    const text = machineDocumentToText(doc, "en");

    expect(text).toContain("[case_01H](/en/ai/staff/reports/case_01H)");
    expect(text).toContain("vulnerability: Yes");
    expect(text).toContain("state: triaged");
  });

  it("describes an owner object and version without media", () => {
    const objectText = machineDocumentToText(
      presentOwnerObjectDetail({
        name: "safety",
        kind: "component",
        stableId: "component_01H",
        versions: [{ version: "1.0", digest: "sha256:abc" }],
        attachedDomains: ["kaspi.kz"],
        labels: {
          objectKind: "object_kind",
          stableId: "stable_id",
          version: "version",
          digest: "digest",
          viewPublic: "View public",
          editPresentation: "Edit",
          versions: "Versions",
          emptyVersions: "None",
          services: "services",
        },
      }),
      "en",
    );
    expect(objectText).toContain("[View public](/en/ai/catalog/components/component_01H)");
    expect(objectText).toContain("[1.0](/en/ai/objects/component/component_01H/versions/1.0)");
    expect(machineTextLeaks(objectText)).toBe(false);

    const versionText = machineDocumentToText(
      presentOwnerVersion({
        name: "safety",
        kind: "component",
        stableId: "component_01H",
        version: "1.0",
        lifecycle: "published",
        visibility: "public",
        digest: "sha256:abc",
        authorVerified: true,
        componentVerified: false,
        installEligible: true,
        labels: {
          ...BOOL,
          objectKind: "object_kind",
          stableId: "stable_id",
          version: "version",
          lifecycle: "lifecycle",
          visibility: "visibility",
          digest: "digest",
          authorVerified: "author_verified",
          componentVerified: "component_verified",
          installEligible: "install_eligible",
        },
      }),
      "en",
    );
    expect(versionText).toContain("visibility: public");
    expect(versionText).toContain("install_eligible: Yes");
  });

  it("keeps publication, invitation and staff facts free of secrets", () => {
    const publication = machineDocumentToText(
      presentPublication({
        title: "Publication",
        subtitle: "Plan",
        planId: "plan_01H",
        state: "ready",
        objectKind: "component",
        stableId: "component_01H",
        version: "1.0",
        digest: "sha256:abc",
        planHash: "sha256:plan",
        policy: "1.0",
        expiresAt: "2026-09-01",
        effects: ["publish"],
        labels: {
          planId: "plan_id",
          state: "state",
          objectKind: "object_kind",
          stableId: "stable_id",
          version: "version",
          digest: "digest",
          planHash: "plan_hash",
          policy: "policy_version",
          expires: "expires_at",
          effects: "effects",
        },
      }),
      "en",
    );
    expect(publication).toContain("plan_id: plan_01H");
    expect(publication).not.toMatch(/device_id|actor_id|csrf/i);

    const invitation = machineDocumentToText(
      presentInvitation({
        title: "Invitation",
        subtitle: "Accept access",
        invitationId: "invitation_01H",
        labels: { invitationId: "invitation_id" },
      }),
      "en",
    );
    expect(invitation).toContain("invitation_id: invitation_01H");
    expect(invitation).not.toMatch(/token|secret/i);

    const staff = machineDocumentToText(
      presentStaffCase({
        title: "Case",
        caseId: "case_01H",
        state: "open",
        vulnerability: false,
        objectKind: "component",
        stableId: "component_01H",
        version: "1.0",
        digest: "sha256:abc",
        errorCode: "",
        harnessId: "claude-code",
        labels: {
          ...BOOL,
          caseId: "case_id",
          state: "state",
          vulnerability: "vulnerability",
          objectKind: "object_kind",
          stableId: "stable_id",
          version: "version",
          digest: "digest",
          errorCode: "error_code",
          harness: "harness",
        },
      }),
      "en",
    );
    expect(staff).toContain("[Staff reports](/en/ai/staff/reports)");
    expect(machineTextLeaks(staff)).toBe(false);
  });

  it("omits media from presentation edit and lists privacy flags", () => {
    const edit = machineDocumentToText(
      presentPresentationEdit({
        title: "Edit",
        note: "Presentation only",
        stableId: "component_01H",
        bio: "Public bio",
        labels: { stableId: "stable_id", bio: "bio" },
      }),
      "en",
    );
    expect(edit).toContain("bio: Public bio");
    expect(edit).not.toMatch(/media|youtube|avatar/i);

    const privacy = machineDocumentToText(
      presentAccountPrivacy({
        title: "Privacy",
        subtitle: "Visibility",
        showProfilePublicly: true,
        allowPublisherListing: false,
        labels: {
          ...BOOL,
          showProfilePublicly: "show_profile_publicly",
          allowPublisherListing: "allow_publisher_listing",
        },
      }),
      "en",
    );
    expect(privacy).toContain("show_profile_publicly: Yes");
    expect(privacy).toContain("allow_publisher_listing: No");
  });

  it("never emits media or icon markup", () => {
    const text = machineDocumentToText(
      presentDevices({
        title: "Devices",
        subtitle: "",
        emptyMessage: "No devices",
        devices: [],
        labels: {
          ...BOOL,
          deviceType: "device_type",
          state: "state",
          lastConnected: "last_active_at",
          approximateLocation: "location",
          locationUnknown: "unknown",
          current: "current",
        },
      }),
      "en",
    );
    expect(text).not.toMatch(/<img|avatar|image\//i);
  });
});
