import { describe, expectTypeOf, it } from "vitest";

import type { PublicGetHeaders, PublicGetOptions } from "@/lib/api/public-http";

describe("publicApiGet type surface", () => {
  it("rejects session tokens and credential headers at compile time", () => {
    type Options = NonNullable<PublicGetOptions>;
    expectTypeOf<Options>().not.toHaveProperty("sessionToken");

    type CookieOk = { Cookie: string } extends PublicGetHeaders ? true : false;
    type AuthOk = { Authorization: string } extends PublicGetHeaders ? true : false;
    type CsrfOk = { "X-CSRF-Token": string } extends PublicGetHeaders ? true : false;
    type AcceptOk = { Accept: string } extends PublicGetHeaders ? true : false;

    expectTypeOf<CookieOk>().toEqualTypeOf<false>();
    expectTypeOf<AuthOk>().toEqualTypeOf<false>();
    expectTypeOf<CsrfOk>().toEqualTypeOf<false>();
    expectTypeOf<AcceptOk>().toEqualTypeOf<true>();
  });
});
