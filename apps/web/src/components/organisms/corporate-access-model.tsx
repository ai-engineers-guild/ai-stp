/* eslint-disable max-lines, max-lines-per-function */
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { NavigationTabs } from "@/components/molecules/navigation-tabs";
import { StatePanel } from "@/components/molecules/state-panel";
import {
  CorporateDetailDrawer,
  PeopleSearch,
  PeopleSelect,
} from "@/components/molecules/people-ui";
import type {
  CorporateEffectivePermission,
  CorporatePermissionDefinition,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";
import {
  CORPORATE_NAV_PAGES,
  corporateNavPageVisible,
  type CorporateNavPage,
} from "@/lib/corporate-navigation";
import { CORPORATE_SECTION_PERMISSIONS, canViewCorporateAdministration } from "@/lib/corporate-hub";
import {
  ACCESS_GROUPS,
  entityDefinitions,
  entityMeta,
  permissionGroup,
  permissionLabel,
  rolePermissions,
  roleTitle,
} from "@/lib/corporate-permission-ui";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

const head = "bg-muted/30 text-muted-foreground px-3 py-3 text-left text-xs font-medium uppercase";
const cell = "px-3 py-3 text-sm";

function sectionPermissions(
  page: CorporateNavPage,
  definitions: readonly CorporatePermissionDefinition[],
) {
  if (page.section === "components") return ["project.list", "member.list"];
  if (page.section) return [CORPORATE_SECTION_PERMISSIONS[page.section] ?? ""].filter(Boolean);
  return page.administration
    ? definitions.map((item) => item.name).filter((name) => canViewCorporateAdministration([name]))
    : [];
}

export function CorporateAccessModel({
  definitions,
  effective,
  roles,
  capabilities,
  view,
}: {
  definitions: readonly CorporatePermissionDefinition[];
  effective: readonly CorporateEffectivePermission[];
  roles: readonly CorporateRoleView[];
  capabilities: readonly string[];
  view: "entities" | "sections";
}) {
  const t = useTranslations("accessUi");
  const h = useTranslations("hub");
  const [query, setQuery] = useState("");
  const [area, setArea] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState("overview");
  const allEntities = entityDefinitions(definitions);
  const entities = allEntities.filter(
    ([resource, items]) =>
      (!area || entityMeta(resource).area === area) &&
      `${t(`entities.${resource}.name`)} ${items.map((item) => `${item.name} ${permissionLabel(item, t)}`).join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const allPages = CORPORATE_NAV_PAGES.filter((page) => page.rail || page.root);
  const pages = allPages.filter(
    (page) =>
      (!area || (page.administration ? "administration" : page.context) === area) &&
      `${h(page.label)} ${page.href} ${t(`sections.${page.id}`)}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const entity = allEntities.find(([resource]) => resource === selected);
  const section = CORPORATE_NAV_PAGES.find((page) => page.id === selected);
  const visibility = (page: CorporateNavPage) =>
    t(
      page.administration
        ? "adminVisibility"
        : page.section
          ? "capabilityVisibility"
          : "authenticatedVisibility",
    );
  function inspect(id: string, tab = "overview") {
    setSelected(id);
    setDetailTab(tab);
  }
  const count = view === "sections" ? pages.length : entities.length;
  return (
    <div
      className={`min-w-0 space-y-5 ${selected ? "2xl:pr-[27rem]" : ""}`}
      data-ui="access-model-workspace"
    >
      <NavigationTabs
        variant="underline"
        ariaLabel={h("accessModel")}
        items={[
          {
            key: "entities",
            label: t("entitiesAndActions"),
            href: "/corporate/admin/access-model",
            active: view === "entities",
          },
          {
            key: "sections",
            label: t("sectionsTab"),
            href: "/corporate/admin/access-model?view=matrix",
            active: view === "sections",
          },
        ]}
      />
      <div className="flex flex-wrap gap-3">
        <PeopleSearch
          label={t(view === "sections" ? "searchSections" : "searchEntities")}
          value={query}
          onChange={setQuery}
        />
        <PeopleSelect
          label={t(view === "sections" ? "allAreas" : "allGroups")}
          value={area}
          onChange={setArea}
          options={[
            ...new Set(
              view === "sections"
                ? allPages.map((page) => (page.administration ? "administration" : page.context))
                : allEntities.map(([resource]) => entityMeta(resource).area),
            ),
          ].map((value) => ({ value, label: t(`areas.${value}`) }))}
        />
      </div>
      {!count ? (
        <StatePanel kind="empty" title={t("noResults")} />
      ) : (
        <div className="border-border overflow-x-auto rounded-lg border">
          {view !== "sections" ? (
            <table
              className="w-full min-w-[58rem] border-collapse"
              aria-label={t("entitiesAndActions")}
            >
              <thead>
                <tr>
                  <th className={head}>{t("entity")}</th>
                  {ACCESS_GROUPS.map((group) => (
                    <th key={group} className={head}>
                      {t(`groups.${group}`)}
                    </th>
                  ))}
                  <th className={`${head} relative`}>
                    <span className="sr-only">{t("details")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {entities.map(([resource, items]) => (
                  <tr key={resource} className="border-border hover:bg-muted/20 border-t">
                    <th scope="row" className={`${cell} min-w-48 text-left`}>
                      <button
                        type="button"
                        onClick={() => {
                          inspect(resource);
                        }}
                        className="focus-visible:ring-ring flex items-center gap-3 rounded-sm text-left focus-visible:ring-2"
                      >
                        <Icon name={entityMeta(resource).icon} />
                        <span>
                          <span className="block font-medium">
                            {t(`entities.${resource}.name`)}
                          </span>
                          <span className="text-muted-foreground block text-xs font-normal">
                            {t(`entities.${resource}.description`)}
                          </span>
                        </span>
                      </button>
                    </th>
                    {ACCESS_GROUPS.map((group) => (
                      <td key={group} className={`${cell} max-w-64`}>
                        <div className="flex flex-wrap gap-1">
                          {items
                            .filter((item) => permissionGroup(item) === group)
                            .map((item) => (
                              <button
                                type="button"
                                key={item.name}
                                onClick={() => {
                                  inspect(resource, "actionsTab");
                                }}
                                title={item.name}
                                className="bg-muted/60 hover:bg-muted focus-visible:ring-ring rounded-sm px-2 py-1 text-xs focus-visible:ring-2"
                              >
                                {permissionLabel(item, t)}
                              </button>
                            ))}
                          {!items.some((item) => permissionGroup(item) === group) ? (
                            <span className="text-muted-foreground">—</span>
                          ) : null}
                        </div>
                      </td>
                    ))}
                    <td className={cell}>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("openDetails", { name: t(`entities.${resource}.name`) })}
                        onClick={() => {
                          inspect(resource);
                        }}
                      >
                        <Icon name="chevronRight" size="sm" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="w-full min-w-[52rem] border-collapse" aria-label={t("sectionsTab")}>
              <thead>
                <tr>
                  {["section", "description", "visibleWhen", "keyPermissions", "area"].map(
                    (key) => (
                      <th key={key} className={head}>
                        {t(key)}
                      </th>
                    ),
                  )}
                  <th className={`${head} relative`}>
                    <span className="sr-only">{t("details")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {pages.map((page) => (
                  <tr key={page.id} className="border-border hover:bg-muted/20 border-t">
                    <th className={`${cell} text-left`} scope="row">
                      <button
                        type="button"
                        onClick={() => {
                          inspect(page.id);
                        }}
                        className="focus-visible:ring-ring flex items-center gap-3 rounded-sm text-left focus-visible:ring-2"
                      >
                        <Icon name={page.icon} />
                        <span>
                          <span className="block font-medium">{h(page.label)}</span>
                          <span className="text-muted-foreground block text-xs font-normal">
                            {page.href}
                          </span>
                        </span>
                      </button>
                    </th>
                    <td className={`${cell} max-w-64`}>{t(`sections.${page.id}`)}</td>
                    <td className={cell}>{visibility(page)}</td>
                    <td className={`${cell} max-w-60`}>
                      <div className="flex flex-wrap gap-1">
                        {sectionPermissions(page, definitions)
                          .slice(0, 3)
                          .map((name) => (
                            <Badge key={name} variant="secondary">
                              {name}
                            </Badge>
                          ))}
                        {sectionPermissions(page, definitions).length > 3 ? (
                          <Badge variant="outline">
                            +{sectionPermissions(page, definitions).length - 3}
                          </Badge>
                        ) : null}
                      </div>
                    </td>
                    <td className={cell}>
                      <Badge variant="secondary" className="font-sans">
                        {t(`areas.${page.administration ? "administration" : page.context}`)}
                      </Badge>
                    </td>
                    <td className={cell}>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("openDetails", { name: h(page.label) })}
                        onClick={() => {
                          inspect(page.id);
                        }}
                      >
                        <Icon name="chevronRight" size="sm" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <p className="text-muted-foreground text-sm">
        {t(view === "sections" ? "sectionCount" : "entityCount", { count })}
      </p>
      <CorporateDetailDrawer
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={
          view === "sections"
            ? t("sectionDetails")
            : entity
              ? t(`entities.${entity[0]}.name`)
              : t("details")
        }
      >
        {view === "sections" && section ? (
          <div className="space-y-5">
            <div className="flex gap-3">
              <Icon name={section.icon} size="lg" />
              <div>
                <h3 className="font-medium">{h(section.label)}</h3>
                <p className="text-muted-foreground text-xs">{section.href}</p>
              </div>
            </div>
            <p className="text-muted-foreground text-sm">{t(`sections.${section.id}`)}</p>
            <div className="border-border space-y-3 border-t pt-4">
              <h3 className="font-medium">{t("visibleWhen")}</h3>
              <p className="text-sm">{visibility(section)}</p>
              <Badge variant="secondary">
                {t(
                  corporateNavPageVisible(section, capabilities)
                    ? "availableToYou"
                    : "unavailableToYou",
                )}
              </Badge>
            </div>
            <div className="border-border space-y-3 border-t pt-4">
              <h3 className="font-medium">{t("keyPermissions")}</h3>
              <div className="flex flex-wrap gap-1">
                {sectionPermissions(section, definitions).map((name) => (
                  <Badge key={name} variant="secondary">
                    {name}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="border-border space-y-3 border-t pt-4">
              <h3 className="font-medium">{t("availableRoles")}</h3>
              {roles
                .filter((role) => corporateNavPageVisible(section, [...rolePermissions(role)]))
                .map((role) => (
                  <Badge key={role.name} variant="secondary" className="mr-1 font-sans">
                    {roleTitle(role.name, t)}
                  </Badge>
                ))}
            </div>
            <Button asChild variant="outline">
              <Link href={section.href}>{t("openSection")}</Link>
            </Button>
          </div>
        ) : entity ? (
          <div className="space-y-4">
            <div className="border-border flex border-b">
              {["overview", "actionsTab"].map((tab) => (
                <Button
                  key={tab}
                  variant="ghost"
                  aria-pressed={detailTab === tab}
                  onClick={() => {
                    setDetailTab(tab);
                  }}
                  className={detailTab === tab ? "border-primary rounded-none border-b-2" : ""}
                >
                  {t(tab)}
                </Button>
              ))}
            </div>
            {detailTab === "overview" ? (
              <>
                <p className="text-muted-foreground text-sm">
                  {t(`entities.${entity[0]}.description`)}
                </p>
                <dl className="border-border bg-muted/20 space-y-3 rounded-lg border p-4 text-sm">
                  <div>
                    <dt className="text-muted-foreground">{t("entityType")}</dt>
                    <dd>{t(`entities.${entity[0]}.name`)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">{t("scope")}</dt>
                    <dd>
                      {[...new Set(entity[1].flatMap((item) => item.scopes))]
                        .map((scope) => t(`scopes.${scope}`))
                        .join(", ")}
                    </dd>
                  </div>
                </dl>
              </>
            ) : null}
            <h3 className="text-sm font-medium">
              {t("availableActions", { count: entity[1].length })}
            </h3>
            {detailTab === "overview" ? (
              <ul className="divide-border divide-y text-sm">
                {entity[1].map((item) => (
                  <li key={item.name} className="py-2">
                    {permissionLabel(item, t)}
                  </li>
                ))}
              </ul>
            ) : (
              <ul className="space-y-2">
                {entity[1].map((item) => (
                  <li
                    key={item.name}
                    className="border-border bg-muted/20 space-y-2 rounded-md border p-3 text-sm"
                  >
                    <p className="font-medium">{permissionLabel(item, t)}</p>
                    <p className="text-muted-foreground font-mono text-xs">{item.name}</p>
                    <Badge variant="secondary">
                      {t(
                        effective.some((grant) => grant.permission === item.name)
                          ? "availableToYou"
                          : "unavailableToYou",
                      )}
                    </Badge>
                    {effective
                      .find((grant) => grant.permission === item.name)
                      ?.source_records.map((source) => (
                        <p
                          key={source.source_id}
                          className="text-muted-foreground text-xs break-all"
                        >
                          {source.role ? roleTitle(source.role, t) : source.kind} ·{" "}
                          {t(`scopes.${source.scope_kind}`)}: {source.scope_id}
                        </p>
                      ))}
                    <div className="flex flex-wrap gap-1">
                      {item.scopes.map((scope) => (
                        <Badge key={scope} variant="outline" className="font-sans">
                          {t(`scopes.${scope}`)}
                        </Badge>
                      ))}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {roles
                        .filter((role) => rolePermissions(role).has(item.name))
                        .map((role) => (
                          <Link
                            key={role.name}
                            href={`/corporate/admin/roles?role=${encodeURIComponent(role.name)}`}
                          >
                            <Badge variant="secondary" className="font-sans">
                              {roleTitle(role.name, t)}
                            </Badge>
                          </Link>
                        ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </CorporateDetailDrawer>
    </div>
  );
}
