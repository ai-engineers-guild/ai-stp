import type { Meta, StoryObj } from "@storybook/react";

import { DeviceList } from "@/components/organisms/device-list";
import type { DeviceRecord } from "@/lib/api/generated/types.gen";
import { deviceList, FIXTURE_DEVICE_ID } from "@/mocks/fixtures/devices";

const meta = {
  title: "UI Kit/Organisms/DeviceList",
  component: DeviceList,
  tags: ["autodocs"],
  args: {
    devices: deviceList.items as DeviceRecord[],
    currentDeviceId: FIXTURE_DEVICE_ID,
    csrfToken: "storybook-csrf-token",
  },
  parameters: {
    docs: {
      description: {
        component:
          "Device cards with approved summary fields and revoke confirmation dialog (Dialog atom).",
      },
    },
  },
} satisfies Meta<typeof DeviceList>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithCurrentDevice: Story = {};

export const Empty: Story = {
  args: {
    devices: [],
    currentDeviceId: null,
  },
};

export const NoCurrentHighlight: Story = {
  args: {
    currentDeviceId: null,
  },
};
