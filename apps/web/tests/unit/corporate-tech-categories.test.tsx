import { entityMenuResult, publicActions } from "../entity-menu-fixture";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { corporateMutation } from "@/lib/api/corporate-mutation";
import type { CategoryView, TechnologyView } from "@/lib/api/generated/types.gen";

const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutation>(),
  refresh: vi.fn(),
}));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: mutation }));
vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(",")}` : key,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { CorporateTechCategories } from "@/components/organisms/corporate-tech-categories";

const org = "organization_fixture";
const capabilities = [
  "category.list",
  "category.read",
  "category.create",
  "category.update",
  "category.delete",
  "technology.list",
  "technology.update",
];

function category(id: string, name: string, revision = 1): CategoryView {
  return {
    schema_version: 1,
    category_id: id,
    area_id: null,
    name,
    description: `${name} description`,
    icon: null,
    provenance: "manual",
    revision,
    state: "active",
  };
}

function technology(id: string, name: string, categoryIds: string[]): TechnologyView {
  return {
    schema_version: 1,
    technology_id: id,
    organization_id: org,
    name,
    description: "",
    aliases: [],
    category_ids: categoryIds,
    icon_url: null,
    official_urls: [],
    lifecycle: "active",
    restore_lifecycle: "active",
    owner_account_id: null,
    provenance: "manual",
    redirect_id: null,
    available_actions: [],
    revision: 2,
  };
}

const categories = [category("cat_lang", "Programming languages"), category("cat_db", "Databases")];
const technologies = [
  technology("tech_ts", "TypeScript", ["cat_lang"]),
  technology("tech_pg", "PostgreSQL", ["cat_db"]),
];

function renderPanel() {
  return render(
    <CorporateTechCategories
      csrfToken="csrf_fixture"
      organizationId={org}
      authorizationRevision={7}
      capabilities={capabilities}
      categories={categories}
      technologies={technologies}
    />,
  );
}

function rowMenu(name: string) {
  const button = screen.getAllByRole("button", { name })[0];
  if (!button) throw new Error(`menu not found: ${name}`);
  return button;
}

afterEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

it("creates a category through POST", async () => {
  mutation.mockResolvedValue({ ok: true, data: { category_id: "cat_new" } });
  const user = userEvent.setup();
  renderPanel();
  await user.click(screen.getByRole("button", { name: "addCategory" }));
  await user.type(screen.getByRole("textbox", { name: "nameRequired" }), "Observability");
  await user.click(screen.getByRole("button", { name: "saveChanges" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalled();
  });
  const call = mutation.mock.calls[0]?.[0];
  expect(call?.method).toBe("POST");
  expect(call?.path).toBe(`/v1/corporate/organizations/${org}/technology-categories`);
  expect(call?.body).toMatchObject({
    state: "active",
    metadata: { name: "Observability" },
    authorization_revision: 7,
  });
  const metadata = (call?.body as { metadata?: { icon?: string } }).metadata;
  expect(metadata?.icon).toMatch(/^lucide:/);
});

it("updates a category with optimistic concurrency", async () => {
  mutation.mockResolvedValue({ ok: true, data: {} });
  const user = userEvent.setup();
  renderPanel();
  await user.click(rowMenu("categoryActions:Databases"));
  await user.click(await screen.findByRole("menuitem", { name: "edit" }));
  const nameInput = screen.getByRole("textbox", { name: "nameRequired" });
  await user.clear(nameInput);
  await user.type(nameInput, "Data stores");
  await user.click(screen.getByRole("button", { name: "saveChanges" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalled();
  });
  const call = mutation.mock.calls[0]?.[0];
  expect(call?.method).toBe("PUT");
  expect(call?.path).toBe(`/v1/corporate/organizations/${org}/technology-categories/cat_db`);
  expect(call?.body).toMatchObject({
    metadata: { name: "Data stores" },
    expected_revision: 1,
  });
});

it("archives a category through the lifecycle endpoint", async () => {
  mutation.mockResolvedValue({ ok: true, data: {} });
  const user = userEvent.setup();
  renderPanel();
  await user.click(rowMenu("categoryActions:Databases"));
  await user.click(await screen.findByRole("menuitem", { name: "deleteCategory" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalled();
  });
  const call = mutation.mock.calls[0]?.[0];
  expect(call?.method).toBe("POST");
  expect(call?.path).toBe(
    `/v1/corporate/organizations/${org}/technology-categories/cat_db/lifecycle`,
  );
  expect(call?.body).toMatchObject({ target: "archived", expected_revision: 1 });
});

it("links technologies to a category by merging category_ids", async () => {
  mutation.mockResolvedValue({ ok: true, data: {} });
  const user = userEvent.setup();
  renderPanel();
  await user.click(rowMenu("categoryActions:Databases"));
  await user.click(await screen.findByRole("menuitem", { name: "manageTechnologies" }));
  await user.click(await screen.findByRole("button", { name: /linkedTechnologies/ }));
  await user.click(await screen.findByRole("checkbox", { name: "TypeScript" }));
  await user.click(screen.getByRole("button", { name: "save" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalled();
  });
  const call = mutation.mock.calls[0]?.[0];
  expect(call?.method).toBe("PUT");
  expect(call?.path).toBe(`/v1/corporate/organizations/${org}/technologies/tech_ts`);
  expect(call?.body).toMatchObject({
    metadata: { name: "TypeScript", category_ids: ["cat_lang", "cat_db"] },
    expected_revision: 2,
  });
});

vi.mock("@/lib/entity-action-query", () => ({
  queryEntityActionMenu: vi.fn((subject: EntityActionSubject) =>
    Promise.resolve(
      entityMenuResult(
        subject,
        [...publicActions.slice(0, -1), "edit", "manage_technologies", "delete", "report"],
        `/corporate/categories/${subject.id}`,
      ),
    ),
  ),
}));
