import type { Meta, StoryObj } from "@storybook/react";

import { Button } from "@/components/atoms/button";
import {
  Menu,
  MenuContent,
  MenuItem,
  MenuSeparator,
  MenuTrigger,
  MenuSub,
  MenuSubTrigger,
  MenuSubContent,
} from "@/components/atoms/menu";
import { Icon } from "@/theme";

const meta = {
  title: "UI Kit/Atoms/Menu",
  component: Menu,
  tags: ["autodocs"],
} satisfies Meta<typeof Menu>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Menu modal={false}>
      <MenuTrigger asChild>
        <Button type="button" variant="outline">
          Actions
        </Button>
      </MenuTrigger>
      <MenuContent>
        <MenuItem>
          <Icon name="link" size="sm" />
          Copy link
        </MenuItem>
        <MenuItem>
          <Icon name="heart" size="sm" />
          Like
        </MenuItem>
        <MenuSeparator />
        <MenuItem disabled>
          <Icon name="flag" size="sm" />
          Report
        </MenuItem>
      </MenuContent>
    </Menu>
  ),
};

export const SharingFlyout: Story = {
  render: () => (
    <Menu modal={false}>
      <MenuTrigger asChild>
        <Button variant="outline">Actions</Button>
      </MenuTrigger>
      <MenuContent>
        <MenuItem>Open details</MenuItem>
        <MenuSub>
          <MenuSubTrigger>Copy and share</MenuSubTrigger>
          <MenuSubContent>
            {["Copy ID", "Copy URL", "Copy CLI command", "Share"].map((label) => (
              <MenuItem key={label}>{label}</MenuItem>
            ))}
          </MenuSubContent>
        </MenuSub>
        <MenuItem>Edit</MenuItem>
      </MenuContent>
    </Menu>
  ),
};

export const LinkItems: Story = {
  render: () => (
    <Menu modal={false}>
      <MenuTrigger asChild>
        <Button type="button" variant="ghost" size="icon" aria-label="Open menu">
          <Icon name="more" size="sm" />
        </Button>
      </MenuTrigger>
      <MenuContent>
        <MenuItem asChild>
          <a href="/catalog">
            <Icon name="objects" size="sm" />
            Catalog
          </a>
        </MenuItem>
        <MenuItem asChild>
          <a href="/docs">
            <Icon name="code" size="sm" />
            Documentation
          </a>
        </MenuItem>
      </MenuContent>
    </Menu>
  ),
};
