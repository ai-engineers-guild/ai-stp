import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  corporateMutationAction,
  corporateTechnologyMergePlanAction,
  corporateProjectUsageAction,
} from "@/actions/corporate";
import type { TechnologyView } from "@/lib/api/generated/types.gen";

const { mutation, refresh, previewMerge, push, loadUsage } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
  push: vi.fn(),
  previewMerge: vi.fn<typeof corporateTechnologyMergePlanAction>(),
  loadUsage: vi.fn<typeof corporateProjectUsageAction>(),
}));
vi.mock("@/actions/corporate", () => ({
  corporateMutationAction: mutation,
  corporateTechnologyMergePlanAction: previewMerge,
  corporateProjectUsageAction: loadUsage,
}));
vi.mock("@/lib/i18n/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));

import {
  TechnologyRegistryCreate,
  TechnologyRegistrySeed,
  TechnologyLifecycleControls,
} from "@/components/organisms/technology-registry-create";
import { TechnologyMergeControls } from "@/components/organisms/technology-merge-controls";
import {
  CategoryLifecycleControls,
  ProjectActivityEditor,
  ProjectLifecycleControls,
  TechnologyActivityPolicy,
} from "@/components/organisms/corporate-governance-controls";

const props = {
  organizationId: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  authorizationRevision: "corporate:organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z:3:1",
  csrfToken: "csrf-fixture",
  categories: null,
};

describe("manual registry creation", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("archives and explicitly restores the same category with acknowledged revisions", async () => {
    mutation.mockResolvedValue({ ok: true, data: {} });
    const category = {
      category_id: "category_known",
      name: "Runtime",
      description: "",
      provenance: "manual",
      state: "active" as const,
      revision: 3,
    };
    render(<CategoryLifecycleControls {...props} category={category} canRemove canRestore />);
    fireEvent.click(screen.getByRole("button", { name: "transition.archived" }));
    await screen.findByText("saved");
    expect(mutation.mock.calls[0]?.[0]).toMatchObject({
      method: "DELETE",
      path: `/v1/corporate/organizations/${props.organizationId}/technology-categories/category_known`,
      body: { expected_revision: 3, authorization_revision: props.authorizationRevision },
    });
    fireEvent.click(screen.getByRole("button", { name: "restore" }));
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledTimes(2);
    });
    expect(mutation.mock.calls[1]?.[0]).toMatchObject({
      method: "POST",
      path: `/v1/corporate/organizations/${props.organizationId}/technology-categories/category_known/lifecycle`,
      body: { expected_revision: 4, target: "active" },
    });
  });

  it("edits a category without replacing its ID and keeps form labels unique", async () => {
    mutation.mockResolvedValue({ ok: false, message: "revision conflict" });
    const category = {
      category_id: "category_00000000000000000000000001",
      name: "Runtime",
      description: "Governed family",
      revision: 3,
      provenance: "manual",
    };
    const { container } = render(
      <>
        <TechnologyRegistryCreate kind="category" {...props} />
        <TechnologyRegistryCreate kind="category" {...props} initialCategory={category} />
      </>,
    );
    const identifiers = [...container.querySelectorAll("[id]")].map((element) => element.id);
    expect(new Set(identifiers).size).toBe(identifiers.length);
    const name = screen.getAllByLabelText("name")[1];
    const form = container.querySelectorAll("form")[1];
    if (!name || !form) throw new Error("category edit form is missing");
    fireEvent.change(name, { target: { value: "Execution runtime" } });
    fireEvent.submit(form);
    await screen.findByText("revision conflict");
    expect(mutation.mock.calls[0]?.[0].path).toMatch(new RegExp(category.category_id + "$"));
    expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
      expected_revision: 3,
      metadata: { name: "Execution runtime" },
    });
  });

  it("previews a merge without writing and retries only the same exact reviewed plan", async () => {
    const source: TechnologyView = {
      schema_version: 1,
      organization_id: props.organizationId,
      technology_id: "technology_00000000000000000000000001",
      owner_account_id: null,
      name: "Source",
      category_ids: ["category_00000000000000000000000001"],
      aliases: [],
      description: "",
      icon_url: null,
      official_urls: [],
      lifecycle: "active",
      restore_lifecycle: "draft",
      revision: 3,
      provenance: "manual",
      redirect_id: null,
      available_actions: [],
    };
    const target: TechnologyView = {
      ...source,
      technology_id: "technology_00000000000000000000000002",
      name: "Target",
      revision: 2,
    };
    const digest = "sha256:" + "a".repeat(64);
    previewMerge.mockResolvedValue({
      ok: true,
      data: {
        source,
        target,
        digest,
        organization_id: props.organizationId,
        affected_project_count: 2,
        affected_team_count: 1,
      },
    });
    mutation.mockResolvedValue({ ok: false, message: "revision conflict" });
    const { container, rerender } = render(
      <TechnologyMergeControls {...props} technology={source} />,
    );
    expect(previewMerge).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("mergeTarget"), {
      target: { value: target.technology_id },
    });
    const form = container.querySelector("form");
    if (!form) throw new Error("merge preview form is missing");
    fireEvent.submit(form);
    await screen.findByRole("button", { name: "mergeApply" });
    expect(mutation).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "mergeApply" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "mergeApply" }));
    await screen.findByText("revision conflict");
    const first = mutation.mock.calls[0]?.[0].body;
    expect(first).toMatchObject({
      target_id: target.technology_id,
      expected_revision: 3,
      target_expected_revision: 2,
      plan_digest: digest,
    });
    rerender(<TechnologyMergeControls {...props} technology={{ ...source, revision: 4 }} />);
    fireEvent.click(screen.getByRole("button", { name: "mergeApply" }));
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledTimes(2);
    });
    expect(mutation.mock.calls[1]?.[0].body).toEqual(first);
    expect(push).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("mergeTarget"), {
      target: { value: source.technology_id },
    });
    expect(screen.queryByRole("button", { name: "mergeApply" })).toBeNull();
  });

  it("retries the exact activity override without inventing activity or rebasing a draft", async () => {
    mutation.mockResolvedValue({ ok: false, message: "revision conflict" });
    const activity = {
      project_id: "remote_project_00000000000000000000000001",
      organization_id: props.organizationId,
      repository_activity_at: null,
      activity_override: null,
      revision: 4,
    };
    const { container, rerender } = render(
      <ProjectActivityEditor {...props} activity={activity} />,
    );
    fireEvent.change(screen.getByLabelText("activityOverride"), { target: { value: "inactive" } });
    fireEvent.change(screen.getByLabelText("source_availability"), {
      target: { value: "unavailable" },
    });
    const form = container.querySelector("form");
    if (!form) throw new Error("activity form is missing");
    fireEvent.submit(form);
    await screen.findByText("revision conflict");
    const first = mutation.mock.calls[0]?.[0].body;
    expect(first).toMatchObject({
      expected_revision: 4,
      repository_activity_at: null,
      activity_override: "inactive",
      source_availability: "unavailable",
      authorization_revision: props.authorizationRevision,
    });
    rerender(<ProjectActivityEditor {...props} activity={{ ...activity, revision: 5 }} />);
    fireEvent.submit(form);
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledTimes(2);
    });
    expect(mutation.mock.calls[1]?.[0].body).toEqual(first);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("restores the tombstoned project explicitly instead of posting an active legacy state", async () => {
    mutation.mockResolvedValue({ ok: true, data: {} });
    render(
      <ProjectLifecycleControls
        {...props}
        project={{
          schema_version: 1,
          project_id: "remote_project_00000000000000000000000001",
          organization_id: props.organizationId,
          name: "Retained",
          state: "archived",
          lifecycle: "deleted",
          restore_lifecycle: "deprecated",
          revision: 6,
          available_actions: [],
        }}
      />,
    );
    expect(screen.queryByText("projectTransition.active")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "restore" }));
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledOnce();
    });
    expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
      target: "restore",
      expected_revision: 6,
    });
    expect(mutation.mock.calls[0]?.[0].path).toMatch(/\/lifecycle$/);
  });

  it("creates an explicit organization activity policy from revision zero", async () => {
    mutation.mockResolvedValue({ ok: true, data: {} });
    const { container } = render(
      <TechnologyActivityPolicy
        {...props}
        policy={{
          organization_id: props.organizationId,
          inactivity_months: 9,
          revision: 0,
        }}
      />,
    );
    fireEvent.change(screen.getByLabelText("inactivityMonths"), { target: { value: "12" } });
    const form = container.querySelector("form");
    if (!form) throw new Error("policy form is missing");
    fireEvent.submit(form);
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledOnce();
    });
    expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
      expected_revision: 0,
      inactivity_months: 12,
    });
  });

  it("pins the edited record revision across capability refresh and preserves the unsaved name", async () => {
    mutation.mockResolvedValue({ ok: false, message: "revision conflict" });
    const initial: TechnologyView = {
      schema_version: 1,
      organization_id: props.organizationId,
      technology_id: "technology_00000000000000000000000001",
      owner_account_id: null,
      name: "Bun",
      category_ids: ["category_00000000000000000000000004"],
      aliases: [],
      description: "",
      official_urls: [],
      icon_url: null,
      lifecycle: "draft",
      restore_lifecycle: "draft",
      revision: 3,
      provenance: "manual",
      redirect_id: null,
      available_actions: [],
    };
    const { container, rerender } = render(
      <TechnologyRegistryCreate kind="technology" {...props} initial={initial} />,
    );
    fireEvent.change(screen.getByLabelText("name"), { target: { value: "Owner draft" } });
    rerender(
      <TechnologyRegistryCreate
        kind="technology"
        {...props}
        initial={{ ...initial, revision: 4, name: "Concurrent edit" }}
      />,
    );
    const form = container.querySelector("form");
    if (!form) throw new Error("edit form is missing");
    fireEvent.submit(form);
    await screen.findByText("revision conflict");
    expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
      expected_revision: 3,
      metadata: { name: "Owner draft" },
    });
    expect(refresh).not.toHaveBeenCalled();
  });

  it("restores an archived draft without approval for an update-only maintainer", async () => {
    mutation.mockResolvedValue({ ok: true, data: {} });
    const technology: TechnologyView = {
      schema_version: 1,
      organization_id: props.organizationId,
      technology_id: "technology_00000000000000000000000001",
      owner_account_id: null,
      name: "Bun",
      category_ids: ["category_00000000000000000000000004"],
      aliases: [],
      description: "",
      icon_url: null,
      official_urls: [],
      lifecycle: "archived",
      restore_lifecycle: "draft",
      revision: 7,
      provenance: "manual",
      redirect_id: null,
      available_actions: [],
    };
    render(
      <TechnologyLifecycleControls
        {...props}
        technology={technology}
        capabilities={["technology.update"]}
      />,
    );
    expect(screen.queryByRole("button", { name: "transition.active" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "restore" }));
    await screen.findByText("saved");
    expect(mutation.mock.calls[0]?.[0]).toMatchObject({
      method: "PATCH",
      body: {
        lifecycle: "draft",
        expected_revision: 7,
        authorization_revision: props.authorizationRevision,
      },
    });
  });

  it("retries the fixed seed effect without changing its key or approving technologies", async () => {
    mutation.mockResolvedValue({ ok: false, message: "request failed" });
    render(<TechnologyRegistrySeed {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "importSeed" }));
    await screen.findByText("request failed");
    const first = mutation.mock.calls[0]?.[0];
    if (!first) throw new Error("seed request is missing");
    expect(first).toMatchObject({
      path: `/v1/corporate/organizations/${props.organizationId}/technology-seed`,
      body: {
        seed_version: 1,
        expected_revision: 0,
        authorization_revision: props.authorizationRevision,
      },
    });
    mutation.mockResolvedValue({ ok: true, data: {} });
    await waitFor(() => expect(screen.getByRole("button", { name: "importSeed" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "importSeed" }));
    await screen.findByText("saved");
    expect(mutation.mock.calls[1]?.[0].body).toEqual(first.body);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("retains the draft and effect key after failure, and allocates a new key for a changed effect", async () => {
    mutation.mockResolvedValue({ ok: false, message: "revision conflict" });
    const { container } = render(<TechnologyRegistryCreate kind="category" {...props} />);
    const name = screen.getByLabelText("name");
    fireEvent.change(name, { target: { value: "Framework" } });
    const form = container.querySelector("form");
    if (!form) throw new Error("creation form is missing");
    fireEvent.submit(form);
    await screen.findByText("revision conflict");
    await waitFor(() => {
      expect(form.getAttribute("aria-busy")).toBe("false");
    });
    expect((name as HTMLInputElement).value).toBe("Framework");
    const first = mutation.mock.calls[0]?.[0];
    if (!first) throw new Error("creation request is missing");
    const firstBody = first.body as { idempotency_key: string };
    expect(first.body).toMatchObject({
      expected_revision: 0,
      authorization_revision: props.authorizationRevision,
      metadata: { name: "Framework" },
    });
    fireEvent.submit(form);
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(form.getAttribute("aria-busy")).toBe("false");
    });
    expect(mutation.mock.calls[1]?.[0].body).toMatchObject({
      idempotency_key: firstBody.idempotency_key,
    });
    fireEvent.change(name, { target: { value: "Runtime" } });
    fireEvent.submit(form);
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledTimes(3);
    });
    expect(mutation.mock.calls[2]?.[0].body).not.toMatchObject({
      idempotency_key: firstBody.idempotency_key,
    });
    expect(refresh).not.toHaveBeenCalled();
  });

  it("allows known category IDs without dictionary discovery and creates no scan prerequisite", async () => {
    mutation.mockResolvedValue({ ok: true, data: {} });
    const { container } = render(<TechnologyRegistryCreate kind="technology" {...props} />);
    fireEvent.change(screen.getByLabelText("name"), { target: { value: "React" } });
    fireEvent.change(screen.getByLabelText("knownCategories"), {
      target: { value: "category_known" },
    });
    fireEvent.change(screen.getByLabelText("aliases"), {
      target: { value: "React.js\n ReactJS " },
    });
    const form = container.querySelector("form");
    if (!form) throw new Error("creation form is missing");
    fireEvent.submit(form);
    await screen.findByText("saved");
    expect(mutation.mock.calls[0]?.[0]).toMatchObject({
      method: "POST",
      path: `/v1/corporate/organizations/${props.organizationId}/technologies`,
      body: {
        metadata: {
          name: "React",
          category_ids: ["category_known"],
          aliases: ["React.js", "ReactJS"],
        },
      },
    });
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
