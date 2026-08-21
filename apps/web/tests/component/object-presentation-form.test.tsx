import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ObjectPresentationForm } from "@/components/organisms/object-presentation-form";

const updateAction = vi.fn<(...args: unknown[]) => unknown>();

vi.mock("@/actions/object-presentation", () => ({
  updateObjectPresentationAction: (...args: unknown[]) => updateAction(...args),
}));

const labels = {
  bio: "Catalog bio",
  media: "Media",
  addMedia: "Add media",
  remove: "Remove",
  kind: "Media type",
  url: "Source",
  alt: "Alternative text",
  caption: "Caption (optional)",
  save: "Save presentation",
  saving: "Saving…",
  saved: "Presentation saved",
  help: "Up to five items.",
  upload: "Upload photo or video",
  uploading: "Uploading…",
  requirements: "JPEG, PNG, WebP, GIF, MP4 or WebM up to 25 MB.",
  youtubeHint: "11-character YouTube video ID",
  githubHint: "Pinned GitHub raw URL",
  youtubePlaceholder: "11-character video ID",
  githubPlaceholder: "https://raw.githubusercontent.com/…",
  invalid: "Fill alt text and a valid source",
  uploadFailed: "Could not upload media.",
  unsupportedType: "Unsupported file type.",
  sizeExceeded: "File is too large.",
  saveFailed: "Could not save presentation.",
  preview: "Media preview",
  uploadInProgress: "Wait for every upload to finish before saving.",
  uploadRequired: "Finish or fix each upload before saving. A local preview is not enough.",
  retryUpload: "Retry upload",
  replaceUpload: "Replace file",
  sourceUpload: "Upload file",
  sourceGithub: "Pinned GitHub raw URL",
  sourceYoutube: "YouTube video ID",
  sourceChoice: "Source",
  uploadedReady: "File uploaded and ready to save.",
  uploadError: "Upload failed",
  itemStatusIdle: "Not ready",
  itemStatusUploading: "Uploading",
  itemStatusReady: "Ready",
  itemStatusError: "Upload failed",
  altRequired: "Required for accessibility.",
  mediaCount: "{count} of {max} items",
  kindImage: "Image",
  kindVideo: "Video",
  kindYoutube: "YouTube",
};

function renderForm(
  initialMedia: Array<{
    kind: "image" | "video" | "youtube";
    url: string;
    alt: string;
    caption: string;
  }> = [{ kind: "image", url: "", alt: "", caption: "" }],
) {
  return render(
    <ObjectPresentationForm
      locale="en"
      stableId="component_01TESTSTABILITY"
      csrfToken="csrf-test"
      initialBio=""
      initialMedia={initialMedia}
      labels={labels}
    />,
  );
}

describe("ObjectPresentationForm media editor", () => {
  beforeEach(() => {
    updateAction.mockReset();
    updateAction.mockResolvedValue({ ok: true });
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          Response.json(
            {
              schema_version: 1,
              media_id: "media_test",
              kind: "image",
              public_url: "/v1/media/component/media_test",
              state: "ready",
            },
            { status: 201 },
          ),
        ),
      ),
    );
  });

  it("uploads a file, shows preview, and saves with the public media path", async () => {
    const user = userEvent.setup();
    renderForm();

    const file = new File([new Uint8Array([137, 80, 78, 71])], "cover.png", {
      type: "image/png",
    });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/objects/component/component_01TESTSTABILITY/media",
        expect.objectContaining({ method: "POST" }),
      );
    });

    await waitFor(() => {
      const preview = document.querySelector('img[src^="data:image"]');
      expect(preview).not.toBeNull();
    });
    expect(await screen.findByText("File uploaded and ready to save.")).toBeTruthy();
    expect(screen.queryByDisplayValue("/v1/media/component/media_test")).toBeNull();

    await user.type(screen.getByLabelText(/Alternative text/i), "Cover alt");
    await user.click(screen.getByRole("button", { name: "Save presentation" }));

    await waitFor(() => {
      expect(updateAction).toHaveBeenCalledWith(
        expect.objectContaining({
          stableId: "component_01TESTSTABILITY",
          media: [
            expect.objectContaining({
              kind: "image",
              url: "/v1/media/component/media_test",
              alt: "Cover alt",
            }),
          ],
        }),
      );
    });
    expect(await screen.findByText("Presentation saved")).toBeTruthy();
  });

  it("blocks unsupported mime types without calling fetch", async () => {
    renderForm();

    const file = new File(["<svg />"], "evil.svg", { type: "image/svg+xml" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect((await screen.findAllByText("Unsupported file type.")).length).toBeGreaterThan(0);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("blocks oversized files without calling fetch", async () => {
    renderForm();
    const big = new File([new Uint8Array(8)], "big.png", { type: "image/png" });
    Object.defineProperty(big, "size", { value: 25 * 1024 * 1024 + 1 });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [big] } });

    expect((await screen.findAllByText("File is too large.")).length).toBeGreaterThan(0);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("surfaces upload failure, keeps local preview, and allows retry", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        Response.json({ message: "Not Found", code: "AI_STP_NOT_FOUND" }, { status: 404 }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderForm();

    const file = new File([new Uint8Array([137, 80, 78, 71])], "cover.png", {
      type: "image/png",
    });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    expect((await screen.findAllByText("Not Found")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(document.querySelector('img[src^="data:image"]')).not.toBeNull();
    });

    await user.type(screen.getByLabelText(/Alternative text/i), "Cover alt");
    await user.click(screen.getByRole("button", { name: "Save presentation" }));
    expect(
      (await screen.findAllByText(/Finish or fix each upload|Not Found/i)).length,
    ).toBeGreaterThan(0);
    expect(updateAction).not.toHaveBeenCalled();

    fetchMock.mockResolvedValueOnce(
      Response.json(
        {
          schema_version: 1,
          media_id: "media_retry",
          kind: "image",
          public_url: "/v1/media/component/media_retry",
          state: "ready",
        },
        { status: 201 },
      ),
    );
    await user.click(screen.getByRole("button", { name: "Retry upload" }));
    expect(await screen.findByText("File uploaded and ready to save.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Save presentation" }));
    await waitFor(() => {
      expect(updateAction).toHaveBeenCalledWith(
        expect.objectContaining({
          media: [expect.objectContaining({ url: "/v1/media/component/media_retry" })],
        }),
      );
    });
  });

  it("blocks save while upload is in flight", async () => {
    const user = userEvent.setup();
    let release!: (value: Response) => void;
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => gate),
    );
    renderForm();

    const file = new File([new Uint8Array([1, 2, 3])], "cover.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    expect(await screen.findByText("Uploading")).toBeTruthy();
    // Primary save control is the submit button; the file control also shows "Uploading…".
    const submit = document.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submit).toBeDisabled();
    expect(submit.textContent).toContain("Uploading");
    expect(updateAction).not.toHaveBeenCalled();

    release(
      Response.json(
        {
          media_id: "media_late",
          kind: "image",
          public_url: "/v1/media/component/media_late",
          state: "ready",
        },
        { status: 201 },
      ),
    );
    await waitFor(() => {
      expect(screen.getByText("File uploaded and ready to save.")).toBeTruthy();
    });
    expect(user).toBeTruthy();
  });

  it("ignores stale upload completion after item removal", async () => {
    const user = userEvent.setup();
    let release!: (value: Response) => void;
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => gate),
    );
    renderForm([
      { kind: "image", url: "", alt: "", caption: "" },
      { kind: "image", url: "", alt: "", caption: "" },
    ]);

    const inputs = document.querySelectorAll('input[type="file"]');
    const firstInput = inputs.item(0);
    if (!(firstInput instanceof HTMLInputElement)) {
      throw new Error("first media file input is missing");
    }
    const file = new File([new Uint8Array([1, 2, 3])], "cover.png", { type: "image/png" });
    await user.upload(firstInput, file);
    const removeButtons = screen.getAllByRole("button", { name: "Remove" });
    const firstRemove = removeButtons.at(0);
    if (!firstRemove) {
      throw new Error("first remove button is missing");
    }
    await user.click(firstRemove);

    release(
      Response.json(
        {
          media_id: "media_stale",
          kind: "image",
          public_url: "/v1/media/component/media_stale",
          state: "ready",
        },
        { status: 201 },
      ),
    );
    await waitFor(() => {
      expect(screen.queryByText("File uploaded and ready to save.")).toBeNull();
    });
    expect(screen.queryByDisplayValue("/v1/media/component/media_stale")).toBeNull();
  });

  it("saves multiple items in order with mixed sources", async () => {
    const user = userEvent.setup();
    renderForm([
      { kind: "image", url: "", alt: "", caption: "" },
      { kind: "youtube", url: "dQw4w9WgXcQ", alt: "Demo", caption: "" },
    ]);

    const file = new File([new Uint8Array([137, 80, 78, 71])], "cover.png", {
      type: "image/png",
    });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);
    await waitFor(() => {
      expect(screen.getByText("File uploaded and ready to save.")).toBeTruthy();
    });

    const altFields = screen.getAllByLabelText(/Alternative text/i);
    const firstAlt = altFields.at(0);
    if (!firstAlt) {
      throw new Error("first alternative text field is missing");
    }
    await user.clear(firstAlt);
    await user.type(firstAlt, "First");
    await user.click(screen.getByRole("button", { name: "Save presentation" }));

    await waitFor(() => {
      expect(updateAction).toHaveBeenCalledWith(
        expect.objectContaining({
          media: [
            expect.objectContaining({
              kind: "image",
              url: "/v1/media/component/media_test",
              alt: "First",
            }),
            expect.objectContaining({
              kind: "youtube",
              url: "dQw4w9WgXcQ",
              alt: "Demo",
            }),
          ],
        }),
      );
    });
  });

  it("exposes accessible per-item status and required labels", () => {
    renderForm();
    expect(screen.getByText("Not ready")).toBeTruthy();
    expect(screen.getByLabelText(/Alternative text/i)).toHaveAttribute("aria-required", "true");
    expect(screen.getByLabelText("Source")).toBeTruthy();
    expect(screen.getByText("Required for accessibility.")).toBeTruthy();
  });

  it("handles non-JSON upload failure without crashing", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("<html>bad gateway</html>", { status: 502 }))),
    );
    renderForm();
    const file = new File([new Uint8Array([1])], "cover.png", { type: "image/png" });
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file);
    expect((await screen.findAllByText("Could not upload media.")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Upload failed").length).toBeGreaterThan(0);
  });
});
