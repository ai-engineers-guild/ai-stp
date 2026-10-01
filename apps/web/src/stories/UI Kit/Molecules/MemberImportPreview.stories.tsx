import type { Meta, StoryObj } from "@storybook/react";
import { NextIntlClientProvider } from "next-intl";
import ru from "../../../../messages/ru.json";
import { MemberImportPreview } from "@/components/molecules/member-import-preview";
import { inspectMemberImport } from "@/lib/member-import";

const rows = inspectMemberImport(
  "email,display_name\nalex@example.com,Alex Morgan\nmaya@example.com,Maya Chen",
);
const meta = {
  title: "UI Kit/Molecules/MemberImportPreview",
  component: MemberImportPreview,
  tags: ["autodocs"],
  globals: { a11y: { manual: true } },
  parameters: { layout: "padded", a11y: { test: "error" } },
  args: { rows },
} satisfies Meta<typeof MemberImportPreview>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Ready: Story = {};
export const Empty: Story = { args: { rows: [] } };
export const Loading: Story = { args: { rows: [], loading: true } };
export const Invalid: Story = {
  args: {
    rows: inspectMemberImport(
      "email,display_name\na@example.com,Alex\na@example.com,Again\nbad,Invalid",
    ),
  },
};
export const LongValues: Story = {
  args: {
    rows: inspectMemberImport(
      `email,display_name\n${"a".repeat(70)}@example.com,${"Name ".repeat(20)}`,
    ),
  },
};
export const Dark: Story = { globals: { theme: "dark" } };
export const Russian: Story = {
  decorators: [
    (Story) => (
      <NextIntlClientProvider locale="ru" messages={ru}>
        <Story />
      </NextIntlClientProvider>
    ),
  ],
};
export const Mobile: Story = { globals: { viewport: { value: "mobile1", isRotated: false } } };
