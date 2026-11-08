import type { Meta, StoryObj } from "@storybook/react";

import { SiteHeader } from "@/components/layouts/site-header";
import { useSessionUiSlice } from "@/lib/stores/session-ui-slice";

/**
 * AppShell is an async Server Component and reads no session: the shell renders
 * statically and the header asks `/api/session` after hydration. Storybook shows
 * the same chrome composition and primes the store the fetch would write to.
 */
function AppShellPreview({
  signedIn,
  children,
}: {
  signedIn: boolean;
  children?: React.ReactNode;
}) {
  useSessionUiSlice.setState({ signedInHint: signedIn });
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded-sm focus:bg-background focus:px-3 focus:py-2 focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>
      <SiteHeader docsHref="http://localhost:8011" />
      <main
        id="main-content"
        className="mx-auto w-full max-w-6xl min-w-0 flex-1 overflow-x-clip px-4 py-10 sm:px-6"
      >
        {children ?? (
          <div className="space-y-2">
            <h1 className="text-3xl font-medium tracking-tight">Page content</h1>
            <p className="text-sm text-muted-foreground">
              Product routes render here inside the shell.
            </p>
          </div>
        )}
      </main>
      <footer className="border-t border-border py-6 text-center text-xs text-muted-foreground">
        ai_stp
      </footer>
    </div>
  );
}

const meta = {
  title: "UI Kit/Layouts/AppShell",
  component: AppShellPreview,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
  args: { signedIn: false },
} satisfies Meta<typeof AppShellPreview>;

export default meta;
type Story = StoryObj<typeof meta>;

export const GuestShell: Story = {
  args: { signedIn: false },
};

export const SignedInShell: Story = {
  args: { signedIn: true },
};

export const CatalogPageChrome: Story = {
  args: { signedIn: false },
  render: (args) => (
    <AppShellPreview signedIn={args.signedIn}>
      <div className="space-y-4">
        <h1 className="text-3xl font-medium">Catalog</h1>
        <p className="text-sm text-muted-foreground">
          Filters + results organisms mount under this shell on `/catalog`.
        </p>
      </div>
    </AppShellPreview>
  ),
};

export const Mobile360: Story = {
  args: { signedIn: false },
  parameters: { viewport: { defaultViewport: "mobile1" } },
};

export const Mobile430SignedIn: Story = {
  args: { signedIn: true },
  parameters: {
    viewport: { defaultViewport: "mobile2" },
    chromatic: { viewports: [360, 430] },
  },
};
