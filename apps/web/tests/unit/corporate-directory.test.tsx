import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { corporateMutationAction } from "@/actions/corporate";
const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
}));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh }),
  Link: ({ children, href, ...props }: { children: ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
import { CorporateDirectory } from "@/components/organisms/corporate-directory";
afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

it("restores directory filters and carries them to the detail page", () => {
  render(
    <CorporateDirectory
      resource="teams"
      items={[
        { id: "mobile", name: "Mobile", state: "active" },
        { id: "old", name: "Mobile legacy", state: "archived" },
      ]}
      organizationId="organization_fixture"
      authorizationRevision={1}
      csrfToken="fixture"
      canCreate={false}
      roles={[]}
      initialQuery="Mobile"
      initialStatus="active"
    />,
  );
  expect(screen.getByLabelText("search")).toHaveValue("Mobile");
  expect(screen.getByLabelText("status")).toHaveValue("active");
  expect(screen.getByRole("link", { name: /Mobile/ })).toHaveAttribute(
    "href",
    "/corporate/teams/mobile?query=Mobile&status=active",
  );
  expect(screen.queryByRole("link", { name: /legacy/ })).not.toBeInTheDocument();
});

it("restores visible rows on history navigation and preserves router history state", () => {
  const routerState = { marker: "router-owned" };
  window.history.replaceState(routerState, "", "/en/corporate/teams");
  render(
    <CorporateDirectory
      resource="teams"
      items={[
        { id: "mobile", name: "Mobile", state: "active" },
        { id: "web", name: "Web", state: "active" },
      ]}
      organizationId="organization_fixture"
      authorizationRevision={1}
      csrfToken="fixture"
      canCreate={false}
      roles={[]}
    />,
  );
  fireEvent.change(screen.getByLabelText("search"), { target: { value: "mobile" } });
  expect(window.history.state).toEqual(routerState);
  expect(window.location.search).toBe("?query=mobile");
  window.history.replaceState(routerState, "", "/en/corporate/teams?query=Web&status=active");
  fireEvent(window, new PopStateEvent("popstate"));
  expect(screen.getByLabelText("search")).toHaveValue("Web");
  expect(screen.getByLabelText("status")).toHaveValue("active");
  expect(screen.queryByRole("link", { name: /Mobile/ })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Web/ })).toHaveAttribute(
    "href",
    "/corporate/teams/web?query=Web&status=active",
  );
});

it("searches projects and preserves a failed creation draft and receipt key on retry", async () => {
  mutation.mockResolvedValue({ ok: false, message: "Please retry" });
  render(
    <CorporateDirectory
      resource="projects"
      items={[
        { id: "mobile", name: "Mobile", state: "active" },
        { id: "web", name: "Web", state: "active" },
      ]}
      organizationId="organization_fixture"
      authorizationRevision={3}
      csrfToken="fixture"
      canCreate
      roles={[]}
    />,
  );
  fireEvent.change(screen.getByLabelText("search"), { target: { value: "mobile" } });
  expect(screen.getByRole("link", { name: /Mobile/ })).toHaveAttribute(
    "href",
    "/corporate/projects/mobile?query=mobile",
  );
  expect(screen.queryByRole("link", { name: /Web/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "create" }));
  fireEvent.change(screen.getByLabelText("name"), { target: { value: "New project" } });
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("name")).toHaveValue("New project");
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await screen.findByRole("alert");
  expect(mutation.mock.calls[1]?.[0].body).toEqual(mutation.mock.calls[0]?.[0].body);
  expect(refresh).not.toHaveBeenCalled();
});
