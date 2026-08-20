import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * REQ-2714 / ADR-0068: raw invitation token must not travel via Server Action.
 * Accept uses fragment → same-origin route handler only.
 */
function walk(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const full = path.join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      files.push(...walk(full));
    } else if (full.endsWith(".ts") || full.endsWith(".tsx")) {
      files.push(full);
    }
  }
  return files;
}

describe("invitation accept transport", () => {
  it("does not expose acceptInvitationAction as a Server Action", () => {
    const actions = readFileSync(path.resolve(__dirname, "../../src/actions/grants.ts"), "utf8");
    expect(actions).not.toContain("acceptInvitationAction");
    expect(actions).not.toContain("acceptGrantInvitation");
  });

  it("client accept component posts to same-origin API route and scrubs fragment", () => {
    const component = readFileSync(
      path.resolve(__dirname, "../../src/components/organisms/accept-invitation.tsx"),
      "utf8",
    );
    expect(component).toContain('"use client"');
    expect(component).toContain("history.replaceState");
    expect(component).toMatch(/\/api\/grants\/invitations\//);
    expect(component).not.toContain("use server");
    expect(component).not.toMatch(/localStorage|sessionStorage/);
  });

  it("route handler accepts body token and never writes it to logs", () => {
    const route = readFileSync(
      path.resolve(
        __dirname,
        "../../src/app/api/grants/invitations/[invitationId]/accept/route.ts",
      ),
      "utf8",
    );
    expect(route).toContain("acceptGrantInvitation");
    expect(route).toContain("assertCsrf");
    expect(route).not.toMatch(/console\.(log|info|debug|warn|error).*token/i);
  });

  it("no client component stores invitation token in browser storage", () => {
    const root = path.resolve(__dirname, "../../src");
    for (const file of walk(root)) {
      const text = readFileSync(file, "utf8");
      if (!text.includes("invitation") && !text.includes("Invitation")) {
        continue;
      }
      expect(text).not.toMatch(/localStorage\.setItem\([^)]*token/i);
      expect(text).not.toMatch(/sessionStorage\.setItem\([^)]*token/i);
    }
  });
});
