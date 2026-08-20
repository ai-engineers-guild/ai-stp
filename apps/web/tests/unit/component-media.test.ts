import { describe, expect, it } from "vitest";

import {
  COMPONENT_MEDIA_MAX_BYTES,
  isGithubRawUrl,
  isUploadedMediaUrl,
  isYoutubeVideoId,
  kindFromMime,
  validateComponentMediaFile,
} from "@/lib/component-media";

describe("component media client bounds", () => {
  it("accepts allowlisted mime and size", () => {
    const file = new File([new Uint8Array(16)], "shot.png", { type: "image/png" });
    expect(validateComponentMediaFile(file)).toBeNull();
    expect(kindFromMime("image/png")).toBe("image");
    expect(kindFromMime("video/webm")).toBe("video");
  });

  it("rejects unsupported mime and oversize payloads", () => {
    const badType = new File([new Uint8Array(8)], "x.gif", { type: "image/svg+xml" });
    expect(validateComponentMediaFile(badType)).toBe("unsupported");
    const huge = new File([new Uint8Array(COMPONENT_MEDIA_MAX_BYTES + 1)], "big.mp4", {
      type: "video/mp4",
    });
    expect(validateComponentMediaFile(huge)).toBe("size");
  });

  it("recognizes safe source shapes", () => {
    expect(isUploadedMediaUrl("/v1/media/component/media_abc")).toBe(true);
    expect(isUploadedMediaUrl("/v1/media/component/media_abc/extra")).toBe(false);
    expect(isGithubRawUrl("https://raw.githubusercontent.com/org/repo/abc/file.png")).toBe(true);
    expect(isYoutubeVideoId("dQw4w9WgXcQ")).toBe(true);
    expect(isYoutubeVideoId("short")).toBe(false);
  });
});
