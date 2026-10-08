import type { Meta, StoryObj } from "@storybook/react";

import { AvatarImage, InitialsAvatar } from "@/components/atoms/avatar-image";

const meta = {
  title: "UI Kit/Atoms/AvatarImage",
  component: AvatarImage,
  tags: ["autodocs"],
  args: {
    src: undefined,
    className: "size-9 rounded-full object-cover",
    fallback: <InitialsAvatar name="Ada Lovelace" />,
  },
} satisfies Meta<typeof AvatarImage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Fallback: Story = {};

export const BrokenSource: Story = {
  args: { src: "/nonexistent/avatar.png" },
};

export const Initials: Story = {
  render: () => (
    <div className="flex items-center gap-3">
      <InitialsAvatar name="Ada Lovelace" />
      <InitialsAvatar name="Grace" />
      <InitialsAvatar name="Tim Berners-Lee" className="size-5 text-[9px]" />
    </div>
  ),
};
