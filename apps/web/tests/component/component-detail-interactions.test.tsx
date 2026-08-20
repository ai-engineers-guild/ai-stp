import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextIntlClientProvider } from "next-intl";
import messages from "../../messages/en.json";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/actions/catalog-reactions", () => ({
  updateCatalogReaction: vi.fn((_kind, _stableId, liked: boolean) =>
    Promise.resolve({ schema_version: 1, liked, likes_count: liked ? 8 : 7 }),
  ),
}));

import { ComponentActions } from "@/components/organisms/component-actions";
import { ComponentMediaGallery } from "@/components/organisms/component-media-gallery";

const labels = {
  copyUrl: "Copy URL",
  share: "Share",
  copyId: "Copy ID",
  copyCli: "Copy CLI command",
  copied: "Copied",
  like: "Like",
  unlike: "Liked",
  more: "More actions",
  report: "Report component",
  editPresentation: "Edit bio and media",
};

describe("component detail interactions", () => {
  const writeText = vi.fn<(value: string) => Promise<void>>().mockResolvedValue(undefined);

  beforeEach(() => {
    writeText.mockClear();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(navigator, "share", { configurable: true, value: undefined });
    window.history.replaceState({}, "", "/en/catalog/components/component_example");
  });

  it("keeps like primary and moves copy/share/report into the overflow", async () => {
    const user = userEvent.setup();
    const clipboardSpy = vi.spyOn(navigator.clipboard, "writeText");
    render(
      <div className="relative">
        <NextIntlClientProvider locale="en" messages={messages}>
          <ComponentActions
            stableId="component_example"
            sharePath="/en/catalog/components/component_example/versions/1.0"
            likesCount={7}
            labels={labels}
            reportHref="/reports?stable_id=component_example"
            editHref="/objects/component/component_example/edit"
            cliCommand="ai-stp registry show component_example@1.0"
          />
        </NextIntlClientProvider>
      </div>,
    );

    expect(screen.getByRole("button", { name: "Like · 7" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Copy ID" })).not.toBeInTheDocument();
    expect(
      screen
        .getByRole("button", { name: "More actions" })
        .querySelector("svg.lucide-ellipsis-vertical"),
    ).not.toBeNull();

    await user.click(screen.getByRole("button", { name: "More actions" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: /Copy ID/ })).toBeVisible();
    expect(within(menu).getByRole("menuitem", { name: /Copy URL/ })).toBeVisible();
    expect(within(menu).getByRole("menuitem", { name: /Copy CLI command/ })).toBeVisible();
    expect(within(menu).getByRole("menuitem", { name: /Edit bio and media/ })).toBeVisible();
    expect(within(menu).getByRole("menuitem", { name: /Report component/ })).toBeVisible();

    await user.click(within(menu).getByRole("menuitem", { name: /Copy ID/ }));
    expect(clipboardSpy).toHaveBeenCalledWith("component_example");

    const like = screen.getByRole("button", { name: "Like · 7" });
    await user.click(like);
    expect(screen.getByRole("button", { name: "Liked · 8" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("copies the canonical version URL from overflow when native share is unavailable", async () => {
    const user = userEvent.setup();
    const clipboardSpy = vi.spyOn(navigator.clipboard, "writeText");
    render(
      <div className="relative">
        <NextIntlClientProvider locale="en" messages={messages}>
          <ComponentActions
            stableId="component_example"
            sharePath="/en/catalog/components/component_example/versions/1.0"
            likesCount={0}
            labels={labels}
            reportHref={undefined}
          />
        </NextIntlClientProvider>
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: /Copy URL/ }));
    expect(clipboardSpy).toHaveBeenCalledWith(
      "http://localhost:3000/en/catalog/components/component_example/versions/1.0",
    );
  });

  it("opens the overflow report action", async () => {
    const user = userEvent.setup();
    render(
      <div className="relative">
        <NextIntlClientProvider locale="en" messages={messages}>
          <ComponentActions
            stableId="component_example"
            sharePath="/en/catalog/components/component_example/versions/1.0"
            likesCount={0}
            labels={labels}
            reportHref="/reports?stable_id=component_example"
          />
        </NextIntlClientProvider>
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: /Report component/ }));
    expect(await screen.findByRole("dialog")).toBeVisible();
    expect(screen.getByDisplayValue(/component_example/)).toBeVisible();
  });

  it("shares the canonical version URL with the native API", async () => {
    const user = userEvent.setup();
    const share = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "share", { configurable: true, value: share });
    render(
      <div className="relative">
        <NextIntlClientProvider locale="en" messages={messages}>
          <ComponentActions
            stableId="component_example"
            sharePath="/en/catalog/components/component_example/versions/1.0"
            likesCount={0}
            labels={labels}
            reportHref={undefined}
          />
        </NextIntlClientProvider>
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: /Share/ }));
    expect(share).toHaveBeenCalledWith({
      url: "http://localhost:3000/en/catalog/components/component_example/versions/1.0",
    });
  });

  it("hides the gallery when media is absent", () => {
    const { container } = render(
      <ComponentMediaGallery
        items={[]}
        labels={{ gallery: "Media", open: "Open media", source: "Source", close: "Close media" }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("opens media in an accessible dialog without a bottom close control", async () => {
    const user = userEvent.setup();
    render(
      <ComponentMediaGallery
        items={[
          {
            id: "media_example",
            kind: "image",
            url: "/catalog-art/agent.webp",
            alt: "Planner preview",
            caption: "Workflow preview",
            source_label: "ai_stp signed storage",
          },
        ]}
        labels={{
          gallery: "Media",
          open: "Open media",
          source: "Source",
          close: "Close media",
          previous: "Previous",
          next: "Next",
        }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Open media: Planner preview" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeVisible();
    expect(screen.getAllByAltText("Planner preview")).toHaveLength(2);
    const close = screen.getByRole("button", { name: "Close media" });
    expect(close).toBeVisible();
    expect(close.className).toContain("top-3");
    expect(close.className).toContain("right-3");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("navigates multiple slides with arrows and keyboard", async () => {
    const user = userEvent.setup();
    render(
      <ComponentMediaGallery
        items={[
          {
            id: "one",
            kind: "image",
            url: "/one.webp",
            alt: "First",
            source_label: "storage",
          },
          {
            id: "two",
            kind: "image",
            url: "/two.webp",
            alt: "Second",
            source_label: "storage",
          },
        ]}
        labels={{
          gallery: "Media",
          open: "Open media",
          source: "Source",
          close: "Close",
          previous: "Previous",
          next: "Next",
        }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Open media: First" }));
    expect(screen.getByText(/1 \/ 2/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(/2 \/ 2/)).toBeVisible();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByText(/1 \/ 2/)).toBeVisible();
  });

  it("does not autoplay video thumbnails", () => {
    render(
      <ComponentMediaGallery
        items={[
          {
            id: "clip",
            kind: "video",
            url: "/clip.mp4",
            alt: "Demo video",
            source_label: "storage",
          },
        ]}
        labels={{ gallery: "Media", open: "Open media", source: "Source", close: "Close" }}
      />,
    );
    const video = document.querySelector("video");
    expect(video).not.toBeNull();
    expect(video?.hasAttribute("autoplay")).toBe(false);
    expect(video?.hasAttribute("controls")).toBe(false);
  });

  it("autoplays an active lightbox video and pauses it on close", async () => {
    const user = userEvent.setup();
    const play = vi.fn().mockResolvedValue(undefined);
    const pause = vi.fn();
    Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: play,
    });
    Object.defineProperty(window.HTMLMediaElement.prototype, "pause", {
      configurable: true,
      value: pause,
    });
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        addEventListener() {},
        removeEventListener() {},
      }),
    });
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(callback: IntersectionObserverCallback) {
          callback(
            [{ isIntersecting: true } as IntersectionObserverEntry],
            this as unknown as IntersectionObserver,
          );
        }
        observe() {}
        disconnect() {}
      },
    );

    render(
      <ComponentMediaGallery
        items={[
          {
            id: "clip",
            kind: "video",
            url: "/clip.mp4",
            alt: "Demo video",
            source_label: "storage",
          },
        ]}
        labels={{ gallery: "Media", open: "Open media", source: "Source", close: "Close media" }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Open media: Demo video" }));
    expect(play).toHaveBeenCalled();
    await user.keyboard("{Escape}");
    expect(pause).toHaveBeenCalled();
  });

  it("keeps overflow actions inside a 360px viewport", async () => {
    const user = userEvent.setup();
    render(
      <div className="relative">
        <NextIntlClientProvider locale="en" messages={messages}>
          <ComponentActions
            stableId="component_example"
            sharePath="/en/catalog/components/component_example/versions/1.0"
            likesCount={7}
            labels={labels}
            reportHref="/reports?stable_id=component_example"
            cliCommand="ai-stp registry show component_example@1.0"
          />
        </NextIntlClientProvider>
      </div>,
    );
    expect(screen.getByRole("button", { name: "Like · 7" })).toHaveClass("min-h-11");
    const more = screen.getByRole("button", { name: "More actions" });
    expect(more).toHaveClass("size-11");
    await user.click(more);
    const menu = await screen.findByRole("menu");
    expect(menu.className).toContain("max-w-[min(20rem,calc(100vw-1.5rem))]");
    expect(within(menu).getByRole("menuitem", { name: /Copy ID/ })).toHaveClass("min-h-11");
  });

  it("shows a deterministic fallback when media cannot load", () => {
    render(
      <ComponentMediaGallery
        items={[
          {
            id: "broken",
            kind: "image",
            url: "https://invalid.test/image.png",
            alt: "Unavailable preview",
            source_label: "Signed storage",
          },
        ]}
        labels={{ gallery: "Media", open: "Open media", source: "Source", close: "Close media" }}
      />,
    );
    fireEvent.error(screen.getByAltText("Unavailable preview"));
    expect(screen.getByRole("img", { name: "Unavailable preview" })).toBeVisible();
    expect(screen.getAllByText("Signed storage").length).toBeGreaterThan(0);
  });
});
