import { describe, expect, it } from "vitest";
import { redact } from "./redact";

describe("redact", () => {
  it("masks bearer material at any depth", () => {
    const env = {
      ok: true,
      data: {
        device_code: "deadbeef",
        nested: { access_token: "tok", client_secret: "s" },
        list: [{ api_key: "k" }],
      },
    };
    const r = redact(env) as typeof env;
    expect(r.data.device_code).toBe("[redacted]");
    expect(r.data.nested.access_token).toBe("[redacted]");
    expect(r.data.nested.client_secret).toBe("[redacted]");
    expect(r.data.list[0].api_key).toBe("[redacted]");
  });

  it("keeps user-facing and diagnostic fields", () => {
    const env = {
      data: {
        user_code: "DKSX-8RAT",
        verification_uri_complete: "https://x/?code=DKSX-8RAT",
        credential_store: "os_keyring",
        id: "task_1",
      },
    };
    const r = redact(env) as typeof env;
    expect(r.data.user_code).toBe("DKSX-8RAT");
    expect(r.data.verification_uri_complete).toContain("DKSX-8RAT");
    expect(r.data.credential_store).toBe("os_keyring");
    expect(r.data.id).toBe("task_1");
  });

  it("passes through scalars and leaves input untouched", () => {
    expect(redact("x")).toBe("x");
    expect(redact(5)).toBe(5);
    const orig = { token: "t" };
    redact(orig);
    expect(orig.token).toBe("t"); // returns a copy, never mutates
  });
});
