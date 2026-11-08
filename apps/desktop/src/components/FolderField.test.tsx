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
import { open } from "@tauri-apps/plugin-dialog";
import FolderField from "./FolderField";

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);
const props = {
  label: "Project folder",
  help: "Existing checkout",
  value: "",
  disabled: false,
};
it("selects one native directory and preserves the path exactly", async () => {
  vi.mocked(open).mockResolvedValue("/project with spaces/каталог");
  const change = vi.fn();
  render(<FolderField {...props} onChange={change} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Choose folder: Project folder" }),
  );
  await waitFor(() =>
    expect(change).toHaveBeenCalledWith("/project with spaces/каталог"),
  );
  expect(open).toHaveBeenCalledWith({
    directory: true,
    multiple: false,
    title: "Project folder",
  });
});
it("keeps the current path when the native dialog is cancelled", async () => {
  vi.mocked(open).mockResolvedValue(null);
  const change = vi.fn();
  render(<FolderField {...props} value="/current" onChange={change} />);
  await act(async () => fireEvent.click(screen.getByRole("button")));
  expect(change).not.toHaveBeenCalled();
  expect(
    (screen.getByLabelText("Project folder") as HTMLInputElement).value,
  ).toBe("/current");
});
it("explains picker failure while leaving manual path entry available", async () => {
  vi.mocked(open).mockRejectedValue(new Error("unavailable"));
  const change = vi.fn();
  render(<FolderField {...props} onChange={change} />);
  fireEvent.click(screen.getByRole("button"));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Paste the full folder path",
  );
  fireEvent.change(screen.getByLabelText("Project folder"), {
    target: { value: "/manual" },
  });
  expect(change).toHaveBeenCalledWith("/manual");
});
it.each(["typed", "locked"])(
  "ignores a late picker reply after the form is %s",
  async (reason) => {
    let reply!: (path: string) => void;
    vi.mocked(open).mockImplementation(
      () =>
        new Promise((resolve) => {
          reply = resolve;
        }),
    );
    const change = vi.fn();
    const view = render(<FolderField {...props} onChange={change} />);
    fireEvent.click(screen.getByRole("button"));
    if (reason === "locked")
      view.rerender(<FolderField {...props} disabled onChange={change} />);
    else
      fireEvent.change(screen.getByLabelText("Project folder"), {
        target: { value: "/typed" },
      });
    change.mockClear();
    await act(async () => reply("/stale"));
    expect(change).not.toHaveBeenCalled();
  },
);
