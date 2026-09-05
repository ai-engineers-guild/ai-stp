---
description: "Review and apply service and country request cases without an HTTP administration API."
last_verified: "2026-09-04"
---

# External catalog requests

Inspect a `service_request` or `country_request` in the staff worklist and verify
its sources. Applying the request requires server and database access:

```sh
python -m ai_stp_platform.external_catalog_admin --case-id report_...
```

The command locks the case, validates its typed payload, writes the service or
country localization, enqueues one deterministic `seo_build` job for each
locale in the same transaction, and sets the case to `resolved`. Repeating an
already resolved case is a no-op. There is no HTTP operation for this effect.

A service request may contain no country codes. Such a service receives its own
localized public page and SEO jobs; it simply does not appear under a country
until a later reviewed request adds that relationship.

After application, verify the case state, both `external_product_locale` rows,
the queued `seo_build` jobs, and the public service or country projection. A
service becomes index-eligible only when both localized descriptions and the
source URL are present.
