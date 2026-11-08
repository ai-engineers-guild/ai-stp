// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ResultMeta } from "./components/Result";

afterEach(cleanup);

it.each([
  [
    "AI_STP_PRECONDITION_FAILED",
    "AI_STP_PRECONDITION_FAILED: Original checkout changed.",
  ],
  ["remote_refusal", "The original server explanation remains available."],
  [null, "The engine returned an explanation without a code."],
])(
  "retains the exact error and its separate machine code: %s",
  (code, message) => {
    render(
      <ResultMeta
        r={{
          ok: false,
          data: null,
          warnings: [],
          continuations: [],
          error_code: code,
          error: message,
        }}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain(message);
    expect(alert.querySelector("code")?.textContent ?? null).toBe(code);
    if (code) expect(alert.textContent?.split(code).length).toBe(2);
  },
);
