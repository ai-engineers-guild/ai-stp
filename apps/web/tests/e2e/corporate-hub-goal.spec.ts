/* eslint-disable max-lines */
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { entityProfileViewSchema } from "../../src/lib/corporate-detail";

/**
 * After integration: run both configured desktop/mobile projects against a fresh
 * corporate standalone artifact. Offline needs corporateHandlers wired into
 * mockFetch. Live needs an authenticated storage-state file, existing populated
 * organization, and same-origin /v1 proxy. Never creates or saves live data.
 * AI_STP_CORPORATE_E2E=offline|live opts in; absent means not part of SaaS E2E.
 */
const mode = process.env["AI_STP_CORPORATE_E2E"];
const state = process.env["AI_STP_CORPORATE_STORAGE_STATE"];
const resources = ["teams", "projects", "technologies", "members"] as const;
const syntheticPngPath = "public/brand/icon-512.png";
const main = (page: Page) => page.locator("#main-content");
test.use({
  ...(mode === "live" && state ? { storageState: state } : {}),
  trace: "off",
  video: "off",
});

async function screenshot(page: Page, info: TestInfo, name: string) {
  const directory = path.resolve(process.cwd(), "../../.impeccable/review");
  await mkdir(directory, { recursive: true });
  const file = path.join(directory, `corporate-goal-${mode}-${info.project.name}-${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await info.attach(name, { path: file, contentType: "image/png" });
}

async function fitsViewport(page: Page) {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
}

async function assertCorporateArtifact(page: Page) {
  await expect(
    page,
    "Corporate E2E requires the corporate_hub artifact; the old SaaS build redirects this path",
  ).toHaveURL(/\/en\/corporate\//);
  await expect(
    page.locator('#site-header [data-ui="nav-overview"]'),
    "Corporate E2E requires the Corporate Hub navigation",
  ).toHaveCount(1);
  await expect(
    page.locator('#site-header [data-ui="nav-services"]'),
    "Corporate E2E must not run against the SaaS navigation",
  ).toHaveCount(0);
}

async function assertMockSessionCookie(page: Page) {
  const pageURL = new URL(page.url());
  const metadata = (await page.context().cookies())
    .filter(({ name }) => name === "ai_stp_session" || name === "ai_stp_csrf")
    .map(({ name, domain, path, secure, expires, httpOnly }) => ({
      name,
      domain,
      path,
      secure,
      expires,
      httpOnly,
    }))
    .sort((left, right) => left.name.localeCompare(right.name));
  console.log(
    `corporate session cookie metadata: ${JSON.stringify({
      page: { hostname: pageURL.hostname, pathname: pageURL.pathname },
      count: metadata.length,
      cookies: metadata,
    })}`,
  );
  expect(
    metadata,
    "Mock auth must persist production-shaped cookies before protected navigation",
  ).toEqual([
    {
      name: "ai_stp_csrf",
      domain: pageURL.hostname,
      path: "/",
      secure: true,
      expires: expect.any(Number),
      httpOnly: false,
    },
    {
      name: "ai_stp_session",
      domain: pageURL.hostname,
      path: "/",
      secure: true,
      expires: expect.any(Number),
      httpOnly: true,
    },
  ]);
}

async function authenticate(page: Page) {
  if (mode === "live") {
    expect(
      Boolean(state),
      "Live corporate verification requires AI_STP_CORPORATE_STORAGE_STATE; no session is fabricated",
    ).toBe(true);
    expect(
      Boolean(process.env["PLAYWRIGHT_EXTERNAL_BASE_URL"]),
      "Live mode requires the actual backend-connected web URL",
    ).toBe(true);
    const me = await page.request.get("/v1/auth/me");
    expect(me.status(), "Existing real API session must be valid").toBe(200);
    return;
  }
  await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Faccount");
  await page.getByRole("button", { name: /Continue with GitHub/i }).click();
  await expect(page).toHaveURL((url) => url.pathname === "/en/corporate/account");
  await assertMockSessionCookie(page);
}

test.describe("original Corporate Hub goal: integrated browser workflow", () => {
  test.skip(
    !mode,
    "Opt in after integration with AI_STP_CORPORATE_E2E=offline or live; this skip is not corporate verification",
  );

  test("anonymous overview keeps the session gate", async ({ browser, baseURL }, info) => {
    expect(["offline", "live"]).toContain(mode);
    const context = await browser.newContext({
      ...(baseURL ? { baseURL } : {}),
      storageState: { cookies: [], origins: [] },
    });
    const page = await context.newPage();
    try {
      await page.goto("/en/corporate/overview");
      await expect(page).toHaveURL(/\/en\/corporate\/login\?returnTo=/);
      expect(new URL(page.url()).searchParams.get("returnTo")).toBe("/en/corporate/overview");
      await expect(page.locator('[data-ui="corporate-overview-tree"]')).toHaveCount(0);
      info.annotations.push({
        type: "backend",
        description:
          mode === "live"
            ? "Actual web session gate"
            : "Offline session gate; not production RBAC evidence",
      });
    } finally {
      await context.close();
    }
  });

  test("overview, four populated directories, details and authorized editors", async ({
    page,
  }, info) => {
    test.setTimeout(180_000);
    page.setDefaultTimeout(15_000);
    expect(["offline", "live"]).toContain(mode);
    info.annotations.push({
      type: "backend",
      description:
        mode === "live"
          ? "Actual backend; editor drafts cancelled, no writes"
          : "Offline fixture transport; not production authorization evidence",
    });
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.name));
    await authenticate(page);
    await page.goto("/en/corporate/overview");
    await assertCorporateArtifact(page);
    await expect(page).toHaveURL(/\/en\/corporate\/overview$/);
    await expect(main(page).getByRole("heading", { level: 1 })).toBeVisible();
    await expect(
      page.locator("#site-header").getByRole("link", { name: "Corporate", exact: true }),
    ).toBeVisible();
    const tree = page.locator('[data-ui="corporate-overview-tree"]');
    await expect(
      tree,
      "A populated authorized organization is required; empty/error screens do not pass",
    ).toBeVisible();
    for (const resource of ["teams", "projects", "members", "technologies"]) {
      await expect(main(page).locator(`a[href$="/corporate/${resource}"]`).first()).toBeVisible();
    }
    const depth = main(page).getByRole("combobox", { name: "Show to", exact: true });
    await expect(depth).toBeVisible();
    await depth.selectOption("0");
    await expect(tree.locator("details[open]")).toHaveCount(0);
    await depth.selectOption("3");
    await expect(tree.locator("details[open]").first()).toBeVisible();
    for (const resource of ["projects", "teams", "members"]) {
      await expect(tree.locator(`a[href*="/corporate/${resource}/"]`).first()).toBeVisible();
    }
    const filter = main(page)
      .locator("details")
      .filter({
        has: page.locator("summary").filter({ hasText: /^Team(?: \(\d+\))?$/ }),
      })
      .first();
    const filterSummary = filter.locator(":scope > summary");
    if (await filterSummary.isVisible()) {
      await filterSummary.click();
      const choices = filter.getByRole("checkbox");
      await expect(choices.first()).toBeVisible();
      expect(
        await choices.count(),
        "Team selection must come from the authorized graph",
      ).toBeGreaterThan(0);
      await choices.first().check();
      if ((await choices.count()) > 1) await choices.nth(1).check();
      await expect(choices.first()).toBeChecked();
      await main(page).getByRole("button", { name: "Clear filters", exact: true }).click();
      await expect(choices.first()).not.toBeChecked();
      await expect(filterSummary).toBeVisible();
      await filterSummary.click();
    } else {
      await main(page).getByRole("button", { name: "Filters", exact: true }).click();
      const filterDialog = page.getByRole("dialog");
      await expect(filterDialog).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(filterDialog).toBeHidden();
    }
    const search = main(page).getByRole("textbox", {
      name: "Search projects, teams and employees",
    });
    await search.fill("__corporate_e2e_no_matching_node__");
    await expect(tree).toHaveCount(0);
    await expect(main(page).getByRole("status")).toBeVisible();
    await search.fill("");
    await expect(tree).toBeVisible();
    await fitsViewport(page);
    await screenshot(page, info, "overview");

    let organizationId = "";
    if (mode === "live") {
      const organizations = await page.request.get("/v1/organizations");
      expect(organizations.status()).toBe(200);
      const body = (await organizations.json()) as {
        items: Array<{ kind: string; organization_id: string }>;
      };
      organizationId = body.items.find((item) => item.kind === "corporate")?.organization_id ?? "";
      expect(
        Boolean(organizationId),
        "Real session must belong to an existing corporate organization",
      ).toBe(true);
    }

    for (const resource of resources) {
      await test.step(`${resource}: directory, search, views, detail and editor`, async () => {
        await page.goto(`/en/corporate/${resource}`);
        const cards = main(page)
          .locator("article")
          .filter({ has: page.locator("h3") });
        await expect(
          cards.first(),
          `The ${resource} directory needs real authorized rows or the explicit offline fixture`,
        ).toBeVisible();
        const name = await cards.first().getByRole("heading").innerText();
        const href = await cards.first().locator("h3 a").getAttribute("href");
        expect(Boolean(href)).toBe(true);
        const directorySearch = page.locator("#directory-search, #employee-search").first();
        await directorySearch.fill("__corporate_e2e_no_matching_card__");
        await expect(cards).toHaveCount(0);
        await directorySearch.fill(name);
        await expect(cards.first()).toBeVisible();
        const list = main(page).getByRole("button", { name: "List", exact: true });
        await list.click();
        await expect(list).toHaveAttribute("aria-pressed", "true");
        await screenshot(page, info, `${resource}-list`);
        const cardView = main(page).getByRole("button", { name: "Cards", exact: true });
        await cardView.click();
        await expect(cardView).toHaveAttribute("aria-pressed", "true");
        await fitsViewport(page);
        await screenshot(page, info, `${resource}-cards`);
        await cards.first().locator("h3 a").click();
        await expect(main(page).getByRole("heading", { level: 1 })).toHaveText(name);
        if (resource === "projects") {
          // Derived from the current corporate-overview and technology fixtures:
          // Platform is owned by Core and currently uses Offline technology.
          const detailMain = main(page).locator('[data-ui="component-detail-main"]');
          const teamsHeading = detailMain.getByRole("heading", {
            level: 2,
            name: "Teams",
            exact: true,
          });
          await expect(teamsHeading).toHaveCount(1);
          await expect(teamsHeading).toBeVisible();
          await expect(
            teamsHeading
              .locator("xpath=ancestor::section[1]")
              .getByRole("link", { name: "Core", exact: true }),
          ).toBeVisible();
          const ownerLabel = main(page)
            .locator('[data-ui="component-detail-rail"]')
            .getByText("Owning team", { exact: true });
          await expect(ownerLabel).toBeVisible();
          await expect(
            ownerLabel.locator("..").getByRole("link", { name: "Core", exact: true }),
          ).toBeVisible();
          const technologiesHeading = detailMain.getByRole("heading", {
            level: 2,
            name: "Technologies",
            exact: true,
          });
          await expect(technologiesHeading).toBeVisible();
          await expect(
            technologiesHeading
              .locator("xpath=ancestor::section[1]")
              .getByRole("link", { name: "Offline technology", exact: true }),
          ).toBeVisible();
          await expect(
            main(page).getByRole("heading", { level: 2, name: "Employees", exact: true }),
          ).toHaveCount(0);
        }
        if (resource === "members") {
          const detailMain = main(page).locator('[data-ui="component-detail-main"]');
          const teamsHeading = detailMain.getByRole("heading", {
            level: 2,
            name: "Teams",
            exact: true,
          });
          await expect(teamsHeading).toBeVisible();
          await expect(
            teamsHeading
              .locator("xpath=ancestor::section[1]")
              .getByRole("link", { name: "Core", exact: true }),
          ).toBeVisible();
        }
        if (resource === "technologies") {
          // The fixture directory owner is the same operational owner shown in the detail rail.
          const detailMain = main(page).locator('[data-ui="component-detail-main"]');
          const ownerLabel = main(page)
            .locator('[data-ui="component-detail-rail"]')
            .getByText("Operational owner", { exact: true });
          await expect(ownerLabel).toBeVisible();
          await expect(
            ownerLabel.locator("..").getByRole("link", { name: "Team lead", exact: true }),
          ).toBeVisible();
          const projectsHeading = detailMain.getByRole("heading", {
            level: 2,
            name: "Projects",
            exact: true,
          });
          await expect(projectsHeading).toHaveCount(1);
          await expect(projectsHeading).toBeVisible();
          await expect(
            projectsHeading
              .locator("xpath=ancestor::section[1]")
              .getByRole("link", { name: "Platform", exact: true }),
          ).toBeVisible();
          await expect(
            main(page).getByText("The landscape is unavailable. Keep your filters and try again.", {
              exact: true,
            }),
          ).toHaveCount(0);
        }
        const id = new URL(href ?? "", page.url()).pathname.split("/").at(-1) ?? "";
        let canEdit = true;
        let before;
        let profilePath = "";
        if (mode === "live") {
          const kind = {
            teams: "team",
            projects: "project",
            technologies: "technology",
            members: "employee",
          }[resource];
          profilePath = `/v1/corporate/organizations/${organizationId}/entity-profiles/${kind}/${id}`;
          const response = await page.request.get(profilePath);
          expect(response.status(), "Integrated profile endpoint must be available").toBe(200);
          before = entityProfileViewSchema.parse(await response.json());
          canEdit = before.can_edit;
        }
        const edit = page.getByRole("menuitem", {
          name: "Edit public presentation",
          exact: true,
        });
        if (resource === "members") {
          await expect(edit).toHaveCount(0);
          return;
        }
        if (!canEdit) {
          await expect(edit).toHaveCount(0);
          await screenshot(page, info, `${resource}-detail-readonly`);
          expect(
            canEdit,
            `${resource}: editor verification requires an actually permitted session; absence is not editor coverage`,
          ).toBe(true);
        }
        await main(page)
          .locator('[data-ui="component-detail-header"]')
          .getByRole("button", { name: "More actions", exact: true })
          .click();
        await expect(edit).toBeVisible();
        await screenshot(page, info, `${resource}-detail`);
        await edit.click();
        await expect(page).toHaveURL(/\/edit$/);
        const description = page.locator("#entity-description");
        await expect(description).toBeVisible();
        const original = await description.inputValue();
        const draftMarker = `Corporate goal browser draft (${info.project.name}-${resource})`;
        const draft = `${original}\n\n**${draftMarker}**`;
        await description.fill(draft);
        const form = main(page).locator('form[aria-label="Edit public presentation"]');
        await form.getByRole("button", { name: "Rendered", exact: true }).click();
        const renderedDraft = form.locator("strong").filter({ hasText: draftMarker });
        await expect(renderedDraft).toHaveCount(1);
        await expect(renderedDraft).toBeVisible();
        await form.getByRole("button", { name: "Plain text", exact: true }).click();
        await expect(description).toHaveValue(draft);
        await fitsViewport(page);
        await screenshot(page, info, `${resource}-editor`);
        await form.getByRole("button", { name: "Cancel", exact: true }).click();
        await expect(description).toHaveCount(0);
        if (mode === "live") {
          const after = await page.request.get(profilePath);
          expect(after.status()).toBe(200);
          expect(entityProfileViewSchema.parse(await after.json())).toEqual(before);
        } else {
          await main(page)
            .locator('[data-ui="component-detail-header"]')
            .getByRole("button", { name: "More actions", exact: true })
            .click();
          await edit.click();
          await expect(description).toHaveValue(original);
          if (resource === "teams") {
            // The corporate editor reuses the component media item widget.
            await expect(form.getByRole("heading", { name: "Media", exact: true })).toBeVisible();
            await expect(form.getByText("Avatar", { exact: true })).toHaveCount(0);
            await form.locator('input[type="file"]').first().setInputFiles(syntheticPngPath);
            await expect(form.locator('img[src^="data:image"]').first()).toBeVisible({
              timeout: 15_000,
            });
            await expect(
              form.getByText("File uploaded and ready to save.", { exact: true }),
            ).toBeVisible({
              timeout: 15_000,
            });
            await form.getByLabel("Alternative text").first().fill("Corporate goal media");
            const linkCount = await form.locator('input[id^="entity-link-"][id$="-label"]').count();
            if (!linkCount) await form.getByRole("button", { name: "Add", exact: true }).click();
            const linkIndex = Math.max(linkCount - 1, 0);
            await form.locator(`#entity-link-${linkIndex}-label`).fill("Corporate docs");
            await form
              .locator(`#entity-link-${linkIndex}-url`)
              .fill("https://example.com/corporate");
          }
          await description.fill(draft);
          await form.getByRole("button", { name: "Save", exact: true }).click();
          await expect(description).toHaveCount(0);
          await page.reload();
          if (resource === "teams") {
            const gallery = main(page).locator('[data-ui="component-media-gallery"]');
            await expect(gallery).toBeVisible();
            const media = gallery.locator("img").last();
            await expect(media).toBeVisible();
            await expect(media).toHaveAttribute("src", /\/v1\/media\/avatars\/avatar_[a-f0-9]{24}/);
            await expect(
              main(page).getByRole("link", { name: "Corporate docs", exact: true }).last(),
            ).toHaveAttribute("href", "https://example.com/corporate");
          }
          await main(page)
            .locator('[data-ui="component-detail-header"]')
            .getByRole("button", { name: "More actions", exact: true })
            .click();
          await edit.click();
          await expect(description).toHaveValue(draft);
          if (resource === "teams") {
            for (const [selector, value] of [
              ['input[id$="-alt"]', "Corporate goal media"],
              ['input[id^="entity-link-"][id$="-label"]', "Corporate docs"],
              ['input[id^="entity-link-"][id$="-url"]', "https://example.com/corporate"],
            ] as const)
              await expect(form.locator(selector).last()).toHaveValue(value);
          }
          await form.getByRole("button", { name: "Cancel", exact: true }).click();
        }
      });
    }
    expect(pageErrors, "Browser runtime errors are failures, even if headings render").toEqual([]);
  });
});
