import { beforeEach, describe, expect, it } from "vitest";

import {
  PROFILE_PREVIEW_STORAGE_KEY,
  readLocalProfilePreview,
  type LocalProfilePreview,
} from "@/lib/profile-preview-storage";

const preview: LocalProfilePreview = {
  accountId: "account_test",
  baseRevisionId: "revision_current",
  baseContentDigest: "sha256:current",
  displayName: "Unsaved name",
  bio: "Unsaved bio",
  links: [{ label: "Docs", url: "https://example.com" }],
  avatarAssetId: null,
  avatarUrl: null,
};

describe("profile preview storage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("restores unsaved fields only for the same server revision", () => {
    window.sessionStorage.setItem(PROFILE_PREVIEW_STORAGE_KEY, JSON.stringify(preview));

    expect(
      readLocalProfilePreview(preview.accountId, preview.baseRevisionId, preview.baseContentDigest),
    ).toEqual(preview);
  });

  it("discards local fields when the server revision has changed", () => {
    window.sessionStorage.setItem(PROFILE_PREVIEW_STORAGE_KEY, JSON.stringify(preview));

    expect(readLocalProfilePreview(preview.accountId, "revision_new", "sha256:new")).toBeNull();
    expect(window.sessionStorage.getItem(PROFILE_PREVIEW_STORAGE_KEY)).toBeNull();
  });
});
