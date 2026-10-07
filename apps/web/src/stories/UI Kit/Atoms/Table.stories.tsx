import type { Meta, StoryObj } from "@storybook/react";

import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";

const meta = {
  title: "UI Kit/Atoms/Table",
  component: Table,
  tags: ["autodocs"],
} satisfies Meta<typeof Table>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Table>
      <THead>
        <Tr>
          <Th>Name</Th>
          <Th>Role</Th>
          <Th>Status</Th>
        </Tr>
      </THead>
      <TBody>
        <Tr>
          <Td>Alice</Td>
          <Td>Admin</Td>
          <Td>Active</Td>
        </Tr>
        <Tr>
          <Td>Bob</Td>
          <Td>Staff</Td>
          <Td>Invited</Td>
        </Tr>
      </TBody>
    </Table>
  ),
};

export const ScrollableWide: Story = {
  render: () => (
    <div className="overflow-x-auto">
      <Table className="min-w-[640px]">
        <THead>
          <Tr>
            <Th>Column</Th>
            <Th>Column</Th>
            <Th>Column</Th>
            <Th>Column</Th>
          </Tr>
        </THead>
        <TBody>
          <Tr>
            <Td>Value</Td>
            <Td>Value</Td>
            <Td>Value</Td>
            <Td>Value</Td>
          </Tr>
        </TBody>
      </Table>
    </div>
  ),
};
