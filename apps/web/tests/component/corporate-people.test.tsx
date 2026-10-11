import { useState, type ReactNode } from "react";
import { NextIntlClientProvider } from "next-intl";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import messages from "../../messages/en.json";
import ru from "../../messages/ru.json";
import { CorporateInviteDialog } from "@/components/organisms/corporate-invite-dialog";
import { PeopleCheckbox } from "@/components/molecules/people-ui";
vi.mock("@/lib/i18n/navigation", () => ({ Link: () => null }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));

function wrap(children: ReactNode) {
  return (
    <NextIntlClientProvider locale="en" messages={messages}>
      {children}
    </NextIntlClientProvider>
  );
}
const defaults = {
  open: true,
  onOpenChange: vi.fn(),
  busy: false,
  error: null,
  roles: ["staff", "lead"],
  teams: [{ value: "team_a", label: "Platform" }],
};
it("requires a role and submits email, optional display name, teams and expiry", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(wrap(<CorporateInviteDialog {...defaults} submit={submit} />));
  await user.type(screen.getByRole("textbox", { name: "Email" }), "alex@company.example");
  await user.click(screen.getByRole("button", { name: "Send invitation" }));
  expect(submit).not.toHaveBeenCalled();
  await user.selectOptions(screen.getByRole("combobox", { name: "Role" }), "lead");
  await user.selectOptions(screen.getByRole("combobox", { name: "Expires in" }), "14");
  const teamsTrigger = document.querySelector("summary");
  if (!teamsTrigger) throw new Error("The team selector was not rendered");
  await user.click(teamsTrigger);
  await user.click(screen.getByRole("checkbox", { name: "Platform" }));
  await user.click(screen.getByRole("button", { name: "Send invitation" }));
  expect(submit).toHaveBeenCalledWith([{ email: "alex@company.example", displayName: "alex" }], {
    role: "lead",
    teamIds: ["team_a"],
    ttlSeconds: 14 * 86400,
  });
});
it("previews bulk input, rejects empty rows, and sends the parsed recipients", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(wrap(<CorporateInviteDialog {...defaults} submit={submit} />));
  await user.click(screen.getByRole("button", { name: "Import from file" }));
  expect(screen.getByRole("button", { name: "Send invitations" })).toBeDisabled();
  await user.click(screen.getByText("Or paste a list", { selector: "summary" }));
  await user.type(
    screen.getByLabelText("Or paste a list"),
    "display_name,email\nAlex,alex@company.example\nInvalid,not-email",
  );
  expect(screen.getByText(/1 recipient ready/)).toBeVisible();
  await user.selectOptions(screen.getByRole("combobox", { name: "Role" }), "staff");
  await user.click(screen.getByRole("button", { name: "Send invitations" }));
  expect(submit).toHaveBeenCalledWith([{ email: "alex@company.example", displayName: "Alex" }], {
    role: "staff",
    teamIds: [],
    ttlSeconds: 7 * 86400,
  });
});
it("keeps errors visible and prevents Escape dismissal while a submission is pending", async () => {
  const user = userEvent.setup();
  const close = vi.fn();
  render(
    wrap(
      <CorporateInviteDialog
        {...defaults}
        onOpenChange={close}
        busy
        error="Authorization changed"
        submit={vi.fn()}
      />,
    ),
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Authorization changed");
  expect(screen.getByRole("button", { name: /Sending/ })).toBeDisabled();
  await user.keyboard("{Escape}");
  expect(close).not.toHaveBeenCalled();
});
it("exposes a partial page selection as a native mixed checkbox", () => {
  render(<PeopleCheckbox label="Select page" checked={false} mixed onChange={vi.fn()} />);
  expect(screen.getByRole("checkbox", { name: "Select page" })).toBePartiallyChecked();
});

it("returns focus to the external invitation button after Escape", async () => {
  const user = userEvent.setup();
  function Example() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button
          type="button"
          onClick={() => {
            setOpen(true);
          }}
        >
          Invite member
        </button>
        <CorporateInviteDialog {...defaults} open={open} onOpenChange={setOpen} submit={vi.fn()} />
      </>
    );
  }
  render(wrap(<Example />));
  const trigger = screen.getByRole("button", { name: "Invite member" });
  await user.click(trigger);
  expect(screen.getByRole("dialog")).toBeVisible();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(trigger).toHaveFocus());
});

it("opens localized import help and preserves role and expiry when changing invitation mode", async () => {
  const user = userEvent.setup();
  render(wrap(<CorporateInviteDialog {...defaults} submit={vi.fn()} />));
  await user.selectOptions(screen.getByRole("combobox", { name: "Role" }), "lead");
  await user.selectOptions(screen.getByRole("combobox", { name: "Expires in" }), "14");
  const help = screen.getByRole("button", { name: "File import help" });
  await user.click(help);
  expect(screen.getByRole("dialog", { name: "File import help" })).toHaveTextContent(
    "email,display_name",
  );
  await user.keyboard("{Escape}");
  await waitFor(() => expect(help).toHaveFocus());
  await user.click(screen.getByRole("button", { name: "Import from file" }));
  expect(screen.getByRole("combobox", { name: "Role" })).toHaveValue("lead");
  expect(screen.getByRole("combobox", { name: "Expires in" })).toHaveValue("14");
  expect(screen.getByRole("table", { name: "Recognized recipients" })).toBeVisible();
});

it("keeps the complete role catalog visible in both invitation modes", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(
    wrap(
      <CorporateInviteDialog
        {...defaults}
        roles={["staff", "lead", "superadmin"]}
        grantableRoles={["superadmin"]}
        submit={submit}
      />,
    ),
  );
  const select = screen.getByRole("combobox", { name: "Role" });
  expect(screen.getByRole("option", { name: "staff — unavailable" })).toBeDisabled();
  expect(screen.getByRole("option", { name: "lead — unavailable" })).toBeDisabled();
  expect(screen.getByRole("option", { name: "superadmin" })).toBeEnabled();
  expect(select).toHaveAccessibleDescription(/permissions you cannot grant/);
  await user.selectOptions(select, "staff");
  expect(select).toHaveValue("");
  await user.selectOptions(select, "superadmin");
  await user.click(screen.getByRole("button", { name: "Import from file" }));
  expect(select).toHaveValue("superadmin");
  expect(screen.getByRole("option", { name: "staff — unavailable" })).toBeDisabled();
  expect(submit).not.toHaveBeenCalled();
});

it("invalidates a selected role when refreshed authority removes it", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  const { rerender } = render(
    wrap(
      <CorporateInviteDialog {...defaults} grantableRoles={["staff", "lead"]} submit={submit} />,
    ),
  );
  await user.type(screen.getByRole("textbox", { name: "Email" }), "alex@example.com");
  await user.selectOptions(screen.getByRole("combobox", { name: "Role" }), "staff");
  rerender(wrap(<CorporateInviteDialog {...defaults} grantableRoles={["lead"]} submit={submit} />));
  expect(screen.getByRole("combobox", { name: "Role" })).toHaveValue("");
  expect(screen.getByRole("button", { name: "Send invitation" })).toBeDisabled();
  const form = screen.getByRole("combobox", { name: "Role" }).closest("form");
  if (!form) throw new Error("The invitation form was not rendered");
  fireEvent.submit(form);
  expect(submit).not.toHaveBeenCalled();
});

it.each([null, []])(
  "distinguishes an authority lookup failure from no assignable roles: %s",
  (grantableRoles) => {
    render(
      <NextIntlClientProvider locale="ru" messages={ru}>
        <CorporateInviteDialog {...defaults} grantableRoles={grantableRoles} submit={vi.fn()} />
      </NextIntlClientProvider>,
    );
    expect(screen.getByRole("option", { name: "staff — недоступна" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      grantableRoles === null ? "Не удалось проверить" : "Нет ролей",
    );
    expect(screen.getByRole("button", { name: "Отправить приглашение" })).toBeDisabled();
  },
);
