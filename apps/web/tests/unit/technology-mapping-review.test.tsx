import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { corporateMutationAction } from "@/actions/corporate";
import type { TechnologyUnmappedEntry, TechnologyView } from "@/lib/api/generated/types.gen";

const { mutation, refresh, push } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh, push }),
  Link: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));

import { TechnologyMappingReview } from "@/components/organisms/technology-mapping-review";

const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const authority = {
  organizationId,
  authorizationRevision: "corporate:organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z:3:1",
  csrfToken: "csrf-fixture",
};

function technology(id: string, name: string): TechnologyView {
  return {
    schema_version: 1,
    technology_id: id,
    organization_id: organizationId,
    owner_account_id: null,
    name,
    description: "",
    aliases: [],
    category_ids: [],
    official_urls: [],
    icon_url: null,
    lifecycle: "active",
    restore_lifecycle: "draft",
    revision: 1,
    redirect_id: null,
    provenance: "manual",
    available_actions: [],
  };
}

const technologies = [
  technology("technology_01JQZK7B8N4M6P2R9T5V0X3Y2B", "PostgreSQL"),
  technology("technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z", "Offline technology"),
];

const openWithCandidate: TechnologyUnmappedEntry = {
  kind: "package",
  coordinate: "package:github.com/jackc/pgx/v5",
  candidate_technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y2B",
  resolved_technology_id: null,
  project_ids: ["project_01JQZK7B8N4M6P2R9T5V0X3Y7Z"],
  state: "open",
};
const openWithoutCandidate: TechnologyUnmappedEntry = {
  kind: "package",
  coordinate: "package:github.com/pressly/goose/v3",
  candidate_technology_id: null,
  resolved_technology_id: null,
  project_ids: ["project_01JQZK7B8N4M6P2R9T5V0X3Y7Z"],
  state: "open",
};
const resolvedEntry: TechnologyUnmappedEntry = {
  kind: "package",
  coordinate: "package:github.com/ogen-go/ogen",
  candidate_technology_id: null,
  resolved_technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  project_ids: ["project_01JQZK7B8N4M6P2R9T5V0X3Y7Z"],
  state: "resolved",
};

function renderReview(
  entries: TechnologyUnmappedEntry[] = [openWithCandidate, openWithoutCandidate, resolvedEntry],
  canUpdate = true,
) {
  return render(
    <TechnologyMappingReview
      {...authority}
      entries={entries}
      technologies={technologies}
      categories={null}
      baseVersion="mapping-fixture-1"
      canUpdate={canUpdate}
    />,
  );
}

beforeEach(() => {
  mutation.mockResolvedValue({ ok: true, data: {} });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("mapping review queue", () => {
  it("lists open coordinates and hides resolved ones by default", () => {
    renderReview();
    expect(screen.getByText(openWithCandidate.coordinate)).toBeInTheDocument();
    expect(screen.getByText(openWithoutCandidate.coordinate)).toBeInTheDocument();
    expect(screen.queryByText(resolvedEntry.coordinate)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "mappingShowResolved" })).toBeInTheDocument();
  });

  it("reveals resolved entries through the toggle", () => {
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "mappingShowResolved" }));
    expect(screen.getByText(resolvedEntry.coordinate)).toBeInTheDocument();
    expect(screen.getByText("mappingResolved")).toBeInTheDocument();
  });

  it("shows the candidate link and draft-free name for a proposed entry", () => {
    renderReview();
    const link = screen.getByRole("link", { name: "PostgreSQL" });
    expect(link).toHaveAttribute(
      "href",
      "/corporate/technologies/technology_01JQZK7B8N4M6P2R9T5V0X3Y2B",
    );
    expect(screen.getByText("mappingCandidate")).toBeInTheDocument();
  });

  it("offers bulk publish only while proposed entries exist", () => {
    const { unmount } = renderReview();
    expect(screen.getByRole("button", { name: "mappingApplyAll" })).toBeInTheDocument();
    unmount();
    render(
      <TechnologyMappingReview
        {...authority}
        entries={[openWithoutCandidate]}
        technologies={technologies}
        categories={null}
        baseVersion={null}
        canUpdate
      />,
    );
    expect(screen.queryByRole("button", { name: "mappingApplyAll" })).not.toBeInTheDocument();
  });

  it("patches a candidate choice through the review endpoint", async () => {
    renderReview();
    const row = screen.getByText(openWithoutCandidate.coordinate).closest("li") as HTMLLIElement;
    fireEvent.change(row.querySelector("select") as HTMLSelectElement, {
      target: { value: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z" },
    });
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledTimes(1);
    });
    expect(mutation.mock.calls[0]?.[0]).toMatchObject({
      method: "PATCH",
      path: `/v1/corporate/organizations/${organizationId}/technology-unmapped-coordinates`,
      body: {
        kind: "package",
        coordinate: openWithoutCandidate.coordinate,
        candidate_technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        authorization_revision: authority.authorizationRevision,
      },
    });
  });

  it("strips every review control without the update capability", () => {
    renderReview([openWithCandidate, openWithoutCandidate, resolvedEntry], false);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "mappingApplyAll" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "mappingApply" })).not.toBeInTheDocument();
  });

  it("renders the empty state when the queue is drained", () => {
    render(
      <TechnologyMappingReview
        {...authority}
        entries={[]}
        technologies={technologies}
        categories={null}
        baseVersion={null}
        canUpdate
      />,
    );
    expect(screen.getByText("mappingQueueEmpty")).toBeInTheDocument();
  });
});
