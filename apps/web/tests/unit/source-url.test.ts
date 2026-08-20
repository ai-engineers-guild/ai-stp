import { describe, expect, it } from "vitest";

import { exactSourceUrl, githubRepositoryUrl, githubSourceUrl } from "@/lib/source-url";

const commit = "a".repeat(40);

describe("exactSourceUrl", () => {
  it("links a source subpath at the exact GitHub commit", () => {
    expect(
      exactSourceUrl({
        repository: "https://github.com/example/project.git",
        commit,
        path: "src/tool",
      }),
    ).toBe(`https://github.com/example/project/tree/${commit}/src/tool`);
  });

  it("links the repository root through the immutable commit page", () => {
    expect(
      exactSourceUrl({ repository: "https://github.com/example/project", commit, path: "" }),
    ).toBe(`https://github.com/example/project/commit/${commit}`);
  });

  it.each([
    "http://github.com/example/project",
    "https://github.com.evil.test/example/project",
    "https://github.com/example/project/extra",
    "https://user@github.com/example/project",
  ])("rejects an unsafe repository URL: %s", (repository) => {
    expect(exactSourceUrl({ repository, commit, path: "src" })).toBeNull();
  });

  it("rejects a movable revision", () => {
    expect(
      exactSourceUrl({
        repository: "https://github.com/example/project",
        commit: "main",
        path: "src",
      }),
    ).toBeNull();
  });

  it("falls back to the repository root when the commit is not exact", () => {
    const source = {
      repository: "https://github.com/example/project.git",
      commit: "main",
      path: "src",
    };
    expect(githubRepositoryUrl(source)).toBe("https://github.com/example/project");
    expect(githubSourceUrl(source)).toBe("https://github.com/example/project");
  });
});
