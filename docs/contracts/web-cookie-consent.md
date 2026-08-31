---
description: "Cookie categories and the rule for starting optional Web integrations."
last_verified: "2026-08-22"
---

# Web cookie consent

| Cookie or storage | Category | Purpose | Before consent |
| --- | --- | --- | --- |
| server session | necessary | Authenticated session | allowed |
| CSRF token | necessary | Protection for mutating requests | allowed |
| `ai_stp_consent` | necessary | Stored category choices | allowed |
| analytics integration | analytics | Aggregated product metrics | prohibited |
| marketing integration | marketing | Future marketing integrations | prohibited |

Rejecting optional categories neither deletes nor disables necessary cookies.
Analytics and marketing are not loaded before an affirmative choice and do not
write cookies or localStorage after rejection. Google Analytics
(`@next/third-parties`) and the official Yandex Metrica counter
`https://mc.yandex.ru/metrika/tag.js` are connected only after consent to the
analytics category and only when `NEXT_PUBLIC_GA_MEASUREMENT_ID` /
`NEXT_PUBLIC_YANDEX_METRIKA_COUNTER_ID` are set (an empty identifier disables
that vendor). `NEXT_PUBLIC_ANALYTICS_ENABLED=false` disables both counters even
when their IDs are set. The banner may be disabled for a deployment without
tracking through `NEXT_PUBLIC_COOKIE_CONSENT_ENABLED=false`; this does not
automatically enable optional integrations.

Server-side detail/download counters under `catalog-usage-metrics.md` are
necessary anti-abuse measures: they set no cookie, start no browser tracker, and
require no analytics consent. This does not permit cohort analytics or a stable
visitor identifier.
