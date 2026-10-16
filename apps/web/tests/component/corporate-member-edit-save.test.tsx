import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { render } from "../render-with-intl";
import messages from "../../messages/en.json";
import { context, member } from "@/stories/UI Kit/Organisms/CorporateMemberRouteDialog.stories";
import { EditMemberDialog } from "@/components/organisms/corporate-member-edit-dialogs";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import type { ReactNode } from "react";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: vi.fn() }));
afterEach(() => {
  vi.clearAllMocks();
});

it("saves a changed member name, closes and keeps role and state intact", async () => {
  vi.mocked(corporateMutation).mockResolvedValue({ ok: true, data: { revision: 1 } });
  const close = vi.fn();
  render(
    <EditMemberDialog
      member={member}
      context={context}
      roles={[]}
      jobTitles={[]}
      csrfToken="csrf"
      onClose={close}
    />,
  );
  fireEvent.change(screen.getByLabelText(messages.corporate.displayName), {
    target: { value: "Ada Updated" },
  });
  await userEvent.click(screen.getByRole("button", { name: messages.corporate.update }));
  await waitFor(() => {
    expect(close).toHaveBeenCalledOnce();
  });
  expect(corporateMutation).toHaveBeenCalledTimes(1);
  expect(vi.mocked(corporateMutation).mock.calls[0]?.[0]).toMatchObject({
    method: "PATCH",
    path: `/v1/corporate/organizations/${context.organization.organization_id}/members/${member.account_id}/profile`,
    body: { display_name: "Ada Updated", expected_revision: 0, authorization_revision: 0 },
  });
});

it("keeps a failed draft in the modal, reports the error and closes with X", async () => {
  vi.mocked(corporateMutation).mockResolvedValue({ ok: false, message: "Write unavailable" });
  const close = vi.fn();
  render(
    <EditMemberDialog
      member={member}
      context={context}
      roles={[]}
      jobTitles={[]}
      csrfToken="csrf"
      onClose={close}
    />,
  );
  fireEvent.change(screen.getByLabelText(messages.corporate.displayName), {
    target: { value: "Ada Draft" },
  });
  await userEvent.click(screen.getByRole("button", { name: messages.corporate.update }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Write unavailable");
  expect(screen.getByDisplayValue("Ada Draft")).toBeVisible();
  expect(close).not.toHaveBeenCalled();
  // The error can render before the saving transition releases the dialog.
  await waitFor(() => {
    expect(screen.getByRole("button", { name: messages.corporate.cancel })).toBeEnabled();
  });
  await userEvent.click(screen.getByRole("button", { name: messages.people.close }));
  expect(close).toHaveBeenCalledOnce();
});
