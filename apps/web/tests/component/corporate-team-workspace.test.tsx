import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi, beforeEach } from "vitest";

import messages from "../../messages/en.json";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import { CorporateResourceActions } from "@/components/organisms/corporate-resource-actions";
import { ProjectionDockView } from "@/components/molecules/projection-dock-view";
import type { ReactNode } from "react";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh, push }),
  usePathname: () => "/corporate/teams",
  Link: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/api/corporate-mutation", () => ({
  corporateMutation: vi.fn(),
}));

function wrap(children: ReactNode) {
  return (
    <NextIntlClientProvider locale="en" messages={messages}>
      {children}
    </NextIntlClientProvider>
  );
}

const resourceProps = {
  csrfToken: "csrf",
  organizationId: "organization_A",
  authorizationRevision: 1,
  resource: "roles" as const,
  resourceId: "auditor",
  name: "auditor",
  rolePermissions: ["team.read"],
  state: "base",
  revision: 1,
  permissions: ["role.update"],
  labels: { ...messages.corporate, title: "Actions" },
};

describe("corporate resource actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it("discards cancelled role permissions on reopen", async () => {
    const user = userEvent.setup();
    render(wrap(<CorporateResourceActions {...resourceProps} />));
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.clear(screen.getByLabelText(messages.corporate.permissions));
    await user.type(screen.getByLabelText(messages.corporate.permissions), "team.write");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(screen.getByLabelText(messages.corporate.permissions)).toHaveValue("team.read");
  });
  it("reuses a failed resource effect key but changes it for an edited draft", async () => {
    const user = userEvent.setup();
    vi.mocked(corporateMutation).mockResolvedValue({ ok: false, message: "Conflict" });
    render(wrap(<CorporateResourceActions {...resourceProps} />));
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: messages.corporate.update }));
    await screen.findByText("Conflict");
    await user.click(await screen.findByRole("button", { name: messages.corporate.update }));
    await waitFor(() => {
      expect(corporateMutation).toHaveBeenCalledTimes(2);
    });
    expect(vi.mocked(corporateMutation).mock.calls[1]?.[0].body).toEqual(
      vi.mocked(corporateMutation).mock.calls[0]?.[0].body,
    );
    await screen.findByRole("button", { name: messages.corporate.update });
    await user.clear(screen.getByLabelText(messages.corporate.permissions));
    await user.type(screen.getByLabelText(messages.corporate.permissions), "team.write");
    await user.click(screen.getByRole("button", { name: messages.corporate.update }));
    await waitFor(() => {
      expect(corporateMutation).toHaveBeenCalledTimes(3);
    });
    expect(vi.mocked(corporateMutation).mock.calls[2]?.[0].body).not.toMatchObject({
      idempotency_key: (
        vi.mocked(corporateMutation).mock.calls[0]?.[0].body as { idempotency_key: string }
      ).idempotency_key,
    });
  });
  it("retains the resource draft and operation key after a transport failure", async () => {
    const user = userEvent.setup();
    vi.mocked(corporateMutation)
      .mockRejectedValueOnce(new Error("Connection lost"))
      .mockResolvedValueOnce({ ok: false, message: "Conflict" });
    render(wrap(<CorporateResourceActions {...resourceProps} />));
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.clear(screen.getByLabelText(messages.corporate.permissions));
    await user.type(screen.getByLabelText(messages.corporate.permissions), "team.write");
    await user.click(screen.getByRole("button", { name: messages.corporate.update }));
    await screen.findByText(messages.common.apiUnavailable);
    expect(screen.getByLabelText(messages.corporate.permissions)).toHaveValue("team.write");
    const retry = await screen.findByRole("button", { name: messages.corporate.update });
    expect(retry).toBeEnabled();
    await user.click(retry);
    await screen.findByText("Conflict");
    expect(vi.mocked(corporateMutation).mock.calls[1]?.[0].body).toEqual(
      vi.mocked(corporateMutation).mock.calls[0]?.[0].body,
    );
  });
});

describe("corporate projection placement", () => {
  it.each([
    ["/en/corporate/teams/team_A?filter=all", "inline"],
    ["/en/login?next=/en/corporate", "fixed"],
  ])("uses only the path of %s", (humanHref, placement) => {
    render(
      <ProjectionDockView
        projection="human"
        humanHref={humanHref}
        machineHref="/en/ai"
        labels={{ group: "Site format", human: "Human", machine: "Machine" }}
      />,
    );
    expect(screen.getByRole("complementary", { name: "Site format" })).toHaveAttribute(
      "data-placement",
      placement,
    );
  });
});
