import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { ObjectOverflowMenu } from "@/components/organisms/component-actions";
import { queryEntityActionMenu } from "@/lib/entity-action-query";
import { loadCatalogOwnerEditor } from "@/actions/entity-actions";
import { corporateAssignContextAction } from "@/actions/corporate";

vi.mock("@/lib/entity-action-query", () => ({ queryEntityActionMenu: vi.fn() }));
vi.mock("@/actions/entity-actions", () => ({ loadCatalogOwnerEditor: vi.fn() }));
vi.mock("@/actions/corporate", () => ({ corporateAssignContextAction: vi.fn() }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/components/organisms/corporate-catalog-owner-editor", () => ({
  CorporateCatalogOwnerDialog: () => null,
}));
vi.mock("@/components/organisms/corporate-assign-dialog", () => ({
  CorporateAssignDialog: () => null,
}));
vi.mock("@/components/organisms/contact-report-dialog", () => ({
  ContactReportDialog: () => null,
}));

it("opens corporate component Edit in place with ownership and relation controls", async () => {
  const subject = {
    kind: "component" as const,
    id: "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    organization_id: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  };
  vi.mocked(queryEntityActionMenu).mockResolvedValue({
    menu: {
      subject,
      href: "/catalog/components/" + subject.id,
      revision: null,
      authorization_revision: 1,
      object_version: "1.0",
      object_name: "Component",
      visibility: "private",
      device_id: null,
      actions: ["edit", "edit_presentation", "change_owner", "assign"].map((id) => ({
        id,
        group: "management" as const,
      })),
    },
    csrfToken: "csrf",
  });
  const origin = window.location.href;
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ObjectOverflowMenu
        stableId={subject.id}
        objectKind="component"
        sharePath={"/catalog/components/" + subject.id}
        reportHref={undefined}
        likesCount={0}
        labels={{
          more: "More",
          copyUrl: "Copy URL",
          copyId: "Copy ID",
          copied: "Copied",
          like: "Like",
          unlike: "Unlike",
          share: "Share",
          report: "Report",
        }}
      />
    </NextIntlClientProvider>,
  );
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "More" }));
  await user.click(await screen.findByRole("menuitem", { name: /^Edit$/ }));
  const dialog = await screen.findByRole("dialog", { name: "Edit" });
  expect(dialog).toBeVisible();
  expect(screen.getByRole("button", { name: messages.hub.assignOwner })).toBeVisible();
  expect(screen.getByRole("button", { name: messages.hub.assign })).toBeVisible();
  expect(window.location.href).toBe(origin);
  await user.click(screen.getByRole("button", { name: messages.hub.assignOwner }));
  await waitFor(() => {
    expect(loadCatalogOwnerEditor).toHaveBeenCalledWith(subject, "1.0");
  });
  expect(screen.queryByRole("dialog", { name: "Edit" })).toBeNull();
  expect(corporateAssignContextAction).not.toHaveBeenCalled();
  vi.mocked(corporateAssignContextAction).mockResolvedValue({ ok: false });
  await user.click(screen.getByRole("button", { name: "More" }));
  await user.click(await screen.findByRole("menuitem", { name: /^Edit$/ }));
  await user.click(screen.getByRole("button", { name: messages.hub.assign }));
  await waitFor(() => {
    expect(corporateAssignContextAction).toHaveBeenCalledOnce();
  });
  expect(screen.queryByRole("dialog", { name: "Edit" })).toBeNull();
  expect(window.location.href).toBe(origin);
});
