// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import CheckoutPreview from "./components/CheckoutPreview";
import type { ContextView } from "./contexts";
import * as transport from "./transport";
import type { CmdResult } from "./transport";

vi.mock("./transport", async (original) => ({
  ...(await original<typeof import("./transport")>()),
  cliPlan: vi.fn(),
  cmdProfileApply: vi.fn(),
}));
const context: ContextView = {
  id: "context_A",
  label: "First",
  mode: "corporate",
  organization: "First company",
  origin: "https://first.example.test",
  connection: "connection_A",
};
const project = { id: "remote_project_fixture", name: "Company project" };
const provider = {
  provider_project_id: "provider_project_fixture",
  provider: "github",
  immutable_repository_id: "42",
  revision: 3,
};
function response(root: string, selected = ""): CmdResult {
  return {
    ok: true,
    data: {
      preview_digest: "sha256:fixture",
      preview: {
        context: {
          context_id: context.id,
          authority: {
            organization: { organization_id: "organization_fixture" },
          },
        },
        account: {
          origin: context.origin,
          connection: { connection_id: context.connection },
        },
        target: {
          organization_id: "organization_fixture",
          remote_project_id: project.id,
          providers: [provider],
        },
        request_coordinates: {
          remote_project_id: project.id,
          provider_project_id: selected || null,
        },
        selected_provider: selected ? provider : null,
        local_project: { root: { path: { display: root, utf8_base64: btoa(root) } } },
        checkout: { checkout: { commit: "a".repeat(40) } },
        online_verified: true,
        observation_only: true,
        installation_authority: false,
        link_created: false,
        binding_created: false,
        request_admitted: false,
      },
    },
    error: null,
    error_code: null,
    warnings: [],
    continuations: [],
  };
}
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);
function view(selected = context, disabled = false) {
  return (
    <CheckoutPreview
      key={`${selected.id}:${project.id}`}
      context={selected}
      project={project}
      disabled={disabled}
    />
  );
}
function fill(root: string) {
  fireEvent.change(screen.getByLabelText("Checkout directory"), {
    target: { value: root },
  });
}
function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Preview checkout" }));
}

it("passes exact paths and the explicit context to native preview, then separately checks a server-provided repository choice", async () => {
  const root = "C:\\Users\\Person\\checkout with spaces";
  vi.mocked(transport.cliPlan)
    .mockResolvedValueOnce(response(root))
    .mockResolvedValueOnce(response(root, provider.provider_project_id));
  render(view());
  expect(transport.cliPlan).not.toHaveBeenCalled();
  fill(root);
  fireEvent.change(screen.getByLabelText("Git executable (optional)"), {
    target: { value: "C:\\Program Files\\Git\\bin\\git.exe" },
  });
  submit();
  await screen.findByText("Checkout verified for review");
  expect(transport.cliPlan).toHaveBeenLastCalledWith(
    "corporate project link-preview",
    {
      context: context.id,
      project: project.id,
      root,
      "git-executable": "C:\\Program Files\\Git\\bin\\git.exe",
    },
  );
  fireEvent.change(screen.getByLabelText("Corporate repository (optional)"), {
    target: { value: provider.provider_project_id },
  });
  expect(screen.queryByText("Checkout verified for review")).toBe(null);
  expect(transport.cliPlan).toHaveBeenCalledTimes(1);
  submit();
  await screen.findByText("Checkout verified for review");
  expect(transport.cliPlan).toHaveBeenLastCalledWith(
    "corporate project link-preview",
    {
      context: context.id,
      project: project.id,
      root,
      "git-executable": "C:\\Program Files\\Git\\bin\\git.exe",
      "provider-project": provider.provider_project_id,
    },
  );
  expect(transport.cmdProfileApply).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: /apply|save|install/i })).toBe(
    null,
  );
  fill("/different checkout");
  expect(screen.queryByText("Checkout verified for review")).toBe(null);
  expect(screen.queryByLabelText("Corporate repository (optional)")).toBe(null);
});

it("drops a late preview after changing away and back to the same context", async () => {
  let finish!: (result: CmdResult) => void;
  vi.mocked(transport.cliPlan)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValueOnce(response("/current checkout"));
  const mounted = render(view());
  fill("/old checkout");
  submit();
  mounted.rerender(
    view({
      ...context,
      id: "context_B",
      origin: "https://second.example.test",
    }),
  );
  mounted.rerender(view());
  expect(
    (screen.getByLabelText("Checkout directory") as HTMLInputElement).value,
  ).toBe("");
  fill("/current checkout");
  submit();
  await screen.findByText("Checkout verified for review");
  await act(async () => {
    finish({ ...response("/old checkout"), warnings: ["Old company warning"] });
  });
  expect(screen.queryByText("/old checkout")).toBe(null);
  expect(screen.queryByText("Old company warning")).toBe(null);
  expect(screen.getByText("/current checkout")).toBeTruthy();
});

it.each(["context", "project", "provider", "link"])(
  "rejects a mismatched %s before rendering response content",
  async (mismatch) => {
    const reply = response("/unrelated checkout");
    const data = reply.data!.preview as Record<string, unknown>;
    if (mismatch === "context") data.context = { context_id: "context_B" };
    if (mismatch === "project")
      data.target = { remote_project_id: "remote_project_other" };
    if (mismatch === "provider") data.selected_provider = provider;
    if (mismatch === "link") data.link_created = true;
    reply.warnings = ["Unrelated company warning"];
    vi.mocked(transport.cliPlan).mockResolvedValue(reply);
    render(view());
    fill("/our checkout");
    submit();
    await screen.findByRole("alert");
    expect(screen.queryByText("/unrelated checkout")).toBe(null);
    expect(screen.queryByText("Unrelated company warning")).toBe(null);
    expect(screen.queryByText("Checkout verified for review")).toBe(null);
  },
);

it("keeps switching or personal views from starting a company checkout read", async () => {
  const mounted = render(view(context, true));
  fill("/checkout");
  submit();
  await waitFor(() => expect(transport.cliPlan).not.toHaveBeenCalled());
  mounted.rerender(
    view({ ...context, id: "context_personal", mode: "personal" }),
  );
  fill("/checkout");
  submit();
  expect(transport.cliPlan).not.toHaveBeenCalled();
});
