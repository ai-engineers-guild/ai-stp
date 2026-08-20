import type { Preview } from "@storybook/react";
import { withThemeByClassName } from "@storybook/addon-themes";

import "../src/app/globals.css";
import { withAppChrome } from "../src/stories/decorators";

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    layout: "padded",
    options: {
      storySort: {
        order: [
          "Foundations",
          ["Introduction", "Colors", "Typography", "Spacing", "Radius", "Icons"],
          "UI Kit",
          [
            "Atoms",
            "Molecules",
            "Organisms",
            [
              "CatalogFilters",
              "CatalogResults",
              "ObjectCard",
              "IdentityList",
              "DeviceList",
              "InstallBlock",
              "ProfileForm",
            ],
            "Layouts",
          ],
        ],
      },
    },
    a11y: {
      test: "todo",
    },
  },
  decorators: [
    withThemeByClassName({
      themes: {
        light: "",
        dark: "dark",
      },
      defaultTheme: "light",
      parentSelector: "html",
    }),
    withAppChrome,
  ],
};

export default preview;
