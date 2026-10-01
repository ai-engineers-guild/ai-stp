import { describe, expect, it } from "vitest";

import { isOutstandingInvitation } from "@/lib/corporate-invitation-state";
import type { CorporateInvitation } from "@/lib/api/generated/types.gen";

const base = {
  invitation_id: "invitation_1",
  recipient_email: "a@b.c",
  display_name: "A",
  role: "staff",
  state: "pending",
  delivery_state: null,
  delivery_error: null,
  expires_at: new Date(Date.now() + 86_400_000).toISOString(),
  created_at: new Date().toISOString(),
  revision: 1,
  token: null,
} as unknown as CorporateInvitation;

describe("isOutstandingInvitation", () => {
  it("keeps only unexpired pending or confirm-pending rows outstanding", () => {
    const future = new Date(Date.now() + 86_400_000).toISOString();
    const past = new Date(Date.now() - 86_400_000).toISOString();
    const cases: [string, string, boolean][] = [
      ["pending", future, true],
      ["email_confirm_pending", future, true],
      ["pending", past, false],
      ["accepted", future, false],
      ["revoked", future, false],
      ["expired", future, false],
    ];
    for (const [state, expires_at, expected] of cases) {
      expect(
        isOutstandingInvitation({ ...base, state, expires_at } as CorporateInvitation),
        `${state} @ ${expires_at}`,
      ).toBe(expected);
    }
  });
});
