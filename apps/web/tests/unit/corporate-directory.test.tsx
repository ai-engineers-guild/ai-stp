import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { corporateMutation } from "@/lib/api/corporate-mutation";
const { mutation, refresh, push } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutation>(),
  refresh: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh, push }),
  usePathname: () => window.location.pathname.replace(/^\/en/, "") || "/",
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
        { id: "mobile", name: "Mobile" },
        { id: "old", name: "Mobile legacy" },
      ]}
      organizationId="organization_fixture"
      authorizationRevision={1}
      csrfToken="fixture"
      canCreate={false}
      roles={[]}
      initialQuery="Mobile"
    />,
  );
  expect(screen.getByLabelText("search")).toHaveValue("Mobile");
  fireEvent.click(screen.getByRole("button", { name: /filters/ }));
  expect(screen.queryByLabelText("status")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Mobile" })).toHaveAttribute(
    "href",
    "/corporate/teams/mobile?query=Mobile",
  );
  expect(screen.getByRole("link", { name: /legacy/ })).toBeVisible();
});

it("shows bounded server pagination and keeps page size in the URL", async () => {
  render(
    <CorporateDirectory
      resource="teams"
      items={[{ id: "team-1", name: "Team one" }]}
      organizationId="organization_fixture"
      authorizationRevision={1}
      csrfToken="fixture"
      canCreate={false}
      roles={[]}
      serverPaginated
      pageNumber={1}
      pageSize={10}
      total={18}
      paginationLabel="Pagination"
    />,
  );
  expect(screen.getByLabelText("Pagination")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "2" })).toHaveAttribute("href", "?page=2");
  fireEvent.change(screen.getByLabelText("pageSize"), { target: { value: "24" } });
  await waitFor(() => {
    expect(push).toHaveBeenCalledWith("/?page_size=24&page=1");
  });
});

it("restores visible rows on history navigation and preserves router history state", async () => {
  const routerState = { marker: "router-owned" };
  window.history.replaceState(routerState, "", "/en/corporate/teams");
  render(
    <CorporateDirectory
      resource="teams"
      items={[
        { id: "mobile", name: "Mobile" },
        { id: "web", name: "Web" },
      ]}
      organizationId="organization_fixture"
      authorizationRevision={1}
      csrfToken="fixture"
      canCreate={false}
      roles={[]}
    />,
  );
  fireEvent.click(screen.getByLabelText("openSearch"));
  fireEvent.change(screen.getByLabelText("search"), { target: { value: "mobile" } });
  await waitFor(() => {
    expect(window.location.search).toBe("?query=mobile");
  });
  expect(window.history.state).toEqual(routerState);
  window.history.replaceState(routerState, "", "/en/corporate/teams?query=Web");
  fireEvent(window, new PopStateEvent("popstate"));
  await waitFor(() => {
    expect(screen.getByLabelText("search")).toHaveValue("Web");
  });
  fireEvent.click(screen.getByRole("button", { name: /filters/ }));
  expect(screen.queryByLabelText("status")).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Mobile/ })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Web/ })).toHaveAttribute(
    "href",
    "/corporate/teams/web?query=Web",
  );
});

it("searches projects and preserves a failed creation draft and receipt key on retry", async () => {
  mutation.mockResolvedValue({ ok: false, message: "Please retry" });
  render(
    <CorporateDirectory
      resource="projects"
      items={[
        { id: "mobile", name: "Mobile" },
        { id: "web", name: "Web" },
      ]}
      organizationId="organization_fixture"
      authorizationRevision={3}
      csrfToken="fixture"
      canCreate
      roles={[]}
    />,
  );
  fireEvent.click(screen.getByLabelText("openSearch"));
  fireEvent.change(screen.getByLabelText("search"), { target: { value: "mobile" } });
  expect(screen.getByRole("link", { name: /Mobile/ })).toHaveAttribute(
    "href",
    "/corporate/projects/mobile?query=mobile",
  );
  expect(screen.queryByRole("link", { name: /Web/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "addProject" }));
  fireEvent.change(screen.getByLabelText("name"), { target: { value: "New project" } });
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("name")).toHaveValue("New project");
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await screen.findByRole("alert");
  expect(mutation.mock.calls[1]?.[0].body).toEqual(mutation.mock.calls[0]?.[0].body);
  expect(refresh).not.toHaveBeenCalled();
});
