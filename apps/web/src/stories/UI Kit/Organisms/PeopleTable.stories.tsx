import type { Meta, StoryObj } from "@storybook/react";

import { PeopleTable, peopleCellClass, peopleHeadClass } from "@/components/molecules/people-ui";

import { withAppChrome } from "../../decorators";

/**
 * Shared administration table shell: labelled scroll region with keyboard
 * access for narrow viewports, `framed` for the bordered-card variant.
 * Callers supply thead/tbody and use `peopleHeadClass`/`peopleCellClass` for
 * consistent header and cell styling.
 */
const meta = {
  title: "UI Kit/Organisms/PeopleTable",
  component: PeopleTable,
  tags: ["autodocs"],
  decorators: [withAppChrome],
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof PeopleTable>;

export default meta;
type Story = StoryObj<typeof meta>;

const rows = [
  ["Alex Morgan", "alex@example.com", "Platform"],
  ["Maya Chen", "maya@example.com", "Design"],
];

function Demo({ framed = false }: { framed?: boolean }) {
  return (
    <div className="p-6">
      <PeopleTable label="Members" minWidth="min-w-[36rem]" framed={framed}>
        <thead>
          <tr className="border-border border-b">
            <th scope="col" className={peopleHeadClass}>
              Name
            </th>
            <th scope="col" className={peopleHeadClass}>
              Email
            </th>
            <th scope="col" className={peopleHeadClass}>
              Team
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, email, team]) => (
            <tr key={email} className="border-border hover:bg-muted/30 border-b last:border-0">
              <td className={`${peopleCellClass} font-medium`}>{name}</td>
              <td className={`${peopleCellClass} text-muted-foreground`}>{email}</td>
              <td className={peopleCellClass}>{team}</td>
            </tr>
          ))}
        </tbody>
      </PeopleTable>
    </div>
  );
}

export const Default: Story = {
  render: () => <Demo />,
};

export const Framed: Story = {
  render: () => <Demo framed />,
};

export const Empty: Story = {
  render: () => (
    <div className="p-6">
      <PeopleTable label="Members" framed>
        <tbody>
          <tr>
            <td className="text-muted-foreground py-14 text-center text-sm">
              No members match your filters.
            </td>
          </tr>
        </tbody>
      </PeopleTable>
    </div>
  ),
};
