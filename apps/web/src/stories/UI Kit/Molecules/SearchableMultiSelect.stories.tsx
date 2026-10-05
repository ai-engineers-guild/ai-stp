import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";

/**
 * Form-native searchable multiselect: renders real `name` checkboxes so the
 * values submit with the enclosing form. `inline` keeps the option list in
 * place (dialogs, filter bars); `modal` moves it into a centered picker;
 * `multiple={false}` turns it into a single-select.
 */
const meta = {
  title: "UI Kit/Molecules/SearchableMultiSelect",
  component: SearchableMultiSelect,
  tags: ["autodocs"],
} satisfies Meta<typeof SearchableMultiSelect>;

export default meta;
type Story = StoryObj<typeof meta>;

const teams = [
  { value: "team_platform", label: "Platform" },
  { value: "team_design", label: "Design" },
  { value: "team_growth", label: "Growth" },
];

function Demo(props: { modal?: boolean; multiple?: boolean; selected?: string[] }) {
  const [selected, setSelected] = useState<string[]>(props.selected ?? ["team_platform"]);
  return (
    <form className="max-w-md space-y-3">
      <SearchableMultiSelect
        name="teams"
        label="Teams"
        searchLabel="Search teams…"
        options={teams}
        selected={selected}
        onChange={setSelected}
        inline
        modal={props.modal}
        multiple={props.multiple}
        emptyHint="Select teams"
        closeLabel="Close"
        selectionSuffix="selected"
      />
    </form>
  );
}

export const Inline: Story = {
  render: () => <Demo />,
};

export const Modal: Story = {
  render: () => <Demo modal />,
};

export const Single: Story = {
  render: () => <Demo multiple={false} />,
};

export const Empty: Story = {
  render: () => <Demo selected={[]} />,
};
