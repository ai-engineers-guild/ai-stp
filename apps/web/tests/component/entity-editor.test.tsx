import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { EntityEditorLayout } from "@/components/molecules/entity-editor-layout";
import { EntityLinksEditor } from "@/components/molecules/entity-links-editor";
import { ENTITY_EDITOR_CONFIGS } from "@/lib/entity-editor-contract";

const labels = {
  title: "Links",
  add: "Add",
  empty: "No links yet.",
  label: "Label",
  url: "URL (HTTPS)",
  remove: "Remove",
};

it("keeps the shared layout identifiable and caps links at five", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const links = Array.from({ length: 5 }, (_, index) => ({
    label: `Link ${index + 1}`,
    url: `https://example.com/${index + 1}`,
  }));

  const { rerender } = render(
    <EntityEditorLayout config={ENTITY_EDITOR_CONFIGS.project} title="Edit project">
      <EntityLinksEditor links={[]} max={5} labels={labels} onChange={onChange} />
    </EntityEditorLayout>,
  );

  expect(screen.getByText("Edit project")).toBeInTheDocument();
  expect(document.querySelector('[data-ui="entity-editor-layout"]')).toHaveAttribute(
    "data-entity-kind",
    "project",
  );
  await user.click(screen.getByRole("button", { name: "Add" }));
  expect(onChange).toHaveBeenCalledWith([{ label: "", url: "https://" }]);

  rerender(
    <EntityEditorLayout config={ENTITY_EDITOR_CONFIGS.project} title="Edit project">
      <EntityLinksEditor links={links} max={5} labels={labels} onChange={onChange} />
    </EntityEditorLayout>,
  );
  expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
});

it("renders configured blocks in the contract order", () => {
  render(
    <EntityEditorLayout
      config={ENTITY_EDITOR_CONFIGS.project}
      title="Edit project"
      blocks={{
        links: <span data-testid="links-block">Links</span>,
        displayName: <span data-testid="name-block">Name</span>,
        avatar: <span data-testid="avatar-block">Avatar</span>,
      }}
    />,
  );

  expect(
    [...document.querySelectorAll('[data-testid$="-block"]')].map((node) => node.textContent),
  ).toEqual(["Name", "Links"]);
});
