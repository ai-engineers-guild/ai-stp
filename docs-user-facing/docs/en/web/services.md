---
title: "Regional services"
description: "The CIS services atlas and how it leads into the catalog."
---

# Regional services

Regional services is a market atlas. You pick a country or an external
service, then open every public component and setup linked to it. The
page does not claim those objects are exclusive to that market, and it
does not install them.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human index | `/{locale}/services` | anyone |
| Machine index | `/{locale}/ai/services` | anyone |
| Human service | `/{locale}/services/{canonical_domain}` | anyone |
| Machine service | `/{locale}/ai/services/{canonical_domain}` | anyone |
| Human country | `/{locale}/countries/{code}` | anyone |
| Machine country | `/{locale}/ai/countries/{code}` | anyone |

The header label is **Regional services**. The footer repeats it under
Product. Anyone may read the atlas. Linking a service to an owned
object is an owner action on [Objects](objects.md), not on this page.

When `NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED` is `false`, service and
country **detail** pages 404. The index may still render an empty
explorer. That is a deployment flag, not a session gate.

## What this screen is for

Use the atlas to:

- see CIS markets as countries;
- filter the service list by country and by service name;
- open a service detail (primary HTTPS URL, countries, linked objects);
- jump into the catalog with country or service filters applied.

The atlas does **not**:

- sell the external product;
- mark a component as only valid in that country;
- create a service (owners do that from an object page);
- run Catalog QL (that stays on [Catalog](catalog.md)).

Listed services are related, not exclusive. A setup can name `kaspi.kz`
and still be usable elsewhere.

## What is on the screen

### Index

The first viewport is a dusk survey plate, title **Regional services**,
and the CIS flag orbit. Below it, compact filters:

| Control | Label | Effect |
| --- | --- | --- |
| Countries | All countries / one code | restricts the service list |
| Services | All services / one domain | restricts further |
| Result count | `N service(s)` | how many match |
| Empty | No services match this combination | clear one filter |

Each visible service shows its name, canonical domain, and countries.
Actions:

| Action | Target |
| --- | --- |
| Service details | `/{locale}/services/{canonical_domain}` |
| Open in catalog | catalog with `service_domain` / `country_code` set |
| Country chip | `/{locale}/countries/{code}` |

**Not specified** in catalog country filters is objects with no country
list. It is not a country on this atlas.

Human / Machine switch keeps the path. Machine index is a list of
services and countries as Markdown links and fields.

### Service detail

| Element | Content |
| --- | --- |
| Kicker | External service |
| Title | service name |
| Link | `canonical_domain` → `primary_url` (HTTPS) |
| SEO summary | when a profile exists |
| Country chips | ISO codes linking to country pages |
| Components and setups | linked public objects |

Object links go to
`/{locale}/catalog/{components\|setups}/{stable_id}`. A missing object
is omitted, not shown as a broken card.

### Country detail

| Element | Content |
| --- | --- |
| Code | ISO country code |
| Title | localized region name |
| Services | services that list this country |
| Components and setups | objects linked to this market |

## Matching CLI commands

There is no `ai-stp services` command. Catalog search is the twin:

```bash
ai-stp registry search --json
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry show --kind setup --id <stable_id> --json
```

Pass the same harness, tag, or author constraints you would use after
leaving the atlas. Country and service filters are website query keys
(`country_codes`, `service_domains`) forwarded to catalog search.

Owners attach services from the CLI-published object, then the website
editor:

```bash
ai-stp owner objects --json
ai-stp owner object show --json
```

The object page **External services** form is documented in
[Objects](objects.md).

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| No services match this combination | both filters too tight | clear country or service |
| Service 404 | unknown domain, or external catalog off | return to the index |
| Country 404 | unknown code, or external catalog off | return to the index |
| Empty Components and setups | nothing linked yet | do not invent objects |
| Open in catalog is empty | catalog filters matched zero | drop a filter; include experimental |
| Primary URL looks untrusted | you left ai_stp | treat it as a third-party site |
| Cannot add a service here | you are not on an owner object | publish in the CLI, then Objects |

The atlas art is original topographic artwork. It is not a live map of
deployments and not a count of installs.

## Related pages

- [Catalog](catalog.md) — `country_code` and `service_domain` filters.
- [Component card](catalog-component.md) — Localization / Linked
  services rail.
- [Setup card](catalog-setup.md) — the same relationships on a setup.
- [Objects](objects.md) — attach or create a service as owner.
- [Catalog (meaning)](../catalog/index.md) — related ≠ exclusive.
- [Publishers](publishers.md) — who published the linked object.

!!! note "HTTPS only"
    A service's primary URL is HTTPS. Do not paste tokens into that
    third-party site from an ai_stp session, and do not put secrets in
    a catalog object to “configure” the service.
