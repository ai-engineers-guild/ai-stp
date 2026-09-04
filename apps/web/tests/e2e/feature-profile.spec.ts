import { expect, test } from "@playwright/test";

const enabled = process.env["AI_STP_EXPECT_CONTENT_HUB"] !== "false";
const saas = process.env["AI_STP_EXPECT_SAAS_PUBLIC_PAGES"] !== "false";

test("compiled content profile is consistent across every public projection", async ({
  page,
  request,
}) => {
  const human = await request.get("/en/content");
  const machine = await request.get("/en/ai/content");
  const detail = await request.get("/en/content/article/kind-skill");
  const feed = await request.get("/feed.xml");
  const draft = await request.get("/en/content/article/internal-draft");
  const contact = await request.get("/en/contact");
  const machineContact = await request.get("/en/ai/contact");
  const privacy = await request.get("/en/legal/privacy");
  expect(human.status()).toBe(enabled ? 200 : 404);
  expect(machine.status()).toBe(enabled ? 200 : 404);
  expect(detail.status()).toBe(enabled ? 200 : 404);
  expect(feed.status()).toBe(enabled ? 200 : 404);
  expect(draft.status()).toBe(404);
  expect(contact.status()).toBe(saas ? 200 : 404);
  expect(machineContact.status()).toBe(saas ? 200 : 404);
  expect(privacy.status()).toBe(saas ? 200 : 404);

  await page.goto("/en");
  await expect(page.locator('[data-ui="nav-content"]')).toHaveCount(enabled ? 1 : 0);
  await expect(page.locator('[data-ui="nav-contact"]')).toHaveCount(saas ? 1 : 0);
  await expect(page.locator('footer a[href$="/contact"]')).toHaveCount(saas ? 1 : 0);
  await expect(page.locator('footer a[href$="/legal/privacy"]')).toHaveCount(saas ? 1 : 0);
  await expect(page.locator('footer a[href$="/legal/cookies"]')).toHaveCount(saas ? 1 : 0);
  const html = await page.content();
  expect(html.includes("/en/content")).toBe(enabled);

  const sitemap = await (await request.get("/sitemap.xml")).text();
  const llms = await (await request.get("/llms.txt")).text();
  const llmsFull = await (await request.get("/llms-full.txt")).text();
  const robots = await (await request.get("/robots.txt")).text();
  expect(sitemap.includes("/en/content")).toBe(enabled);
  expect(sitemap.includes("/en/contact")).toBe(saas);
  expect(sitemap.includes("/en/legal/privacy")).toBe(saas);
  expect(llms.includes("/en/content")).toBe(enabled);
  expect(llmsFull.includes("kind-skill")).toBe(enabled);
  expect(robots.includes("Allow: /en/content")).toBe(enabled);
  expect(robots.includes("Disallow: /en/legal")).toBe(!saas);

  if (enabled) {
    await page.goto("/en/content/article/kind-skill");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("workflow package");
    await expect(page.locator('script[type="application/ld+json"]')).toHaveCount(1);
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      /\/en\/content\/article\/kind-skill$/,
    );
    await expect(page.locator('link[hreflang="ru"]')).toHaveAttribute(
      "href",
      /\/ru\/content\/article\/kind-skill$/,
    );
    await expect(page.locator('meta[property="og:type"]')).toHaveAttribute("content", "article");
    const feedBody = await feed.text();
    expect(feedBody).toContain('<feed xmlns="http://www.w3.org/2005/Atom">');
    expect(feedBody).toMatch(/<link href="https?:\/\//);
    expect(feedBody).not.toContain("internal-draft");
    expect(await machine.text()).not.toEqual(await human.text());
    await expect(page.locator('[data-ui="human-machine-toggle"]')).toBeVisible();
    await expect(page.locator('[data-ui="projection-machine"]')).toHaveAttribute(
      "href",
      "/en/ai/content/article/kind-skill",
    );
    await page.goto("/ru/content/article/kind-skill");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "\u043f\u0430\u043a\u0435\u0442 \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430",
    );
  } else {
    const body = await human.text();
    expect(body).toMatch(/noindex/i);
  }

  if (saas) {
    await page.goto("/en/contact?from=test");
    await expect(page.locator('[data-ui="human-machine-toggle"]')).toBeVisible();
    await expect(page.locator('[data-ui="projection-machine"]')).toHaveAttribute(
      "href",
      "/en/ai/contact?from=test",
    );
    await page.goto("/en/legal/cookies");
    await expect(page.locator('[data-ui="projection-machine"]')).toHaveAttribute(
      "href",
      "/en/ai/legal/cookies",
    );
    await page.locator('[data-ui="projection-machine"]').click();
    await expect(page).toHaveURL(/\/en\/ai\/legal\/cookies$/);
    await expect(page.locator('[data-ui="machine-page-projection"]')).toContainText(
      "# Cookie Policy",
    );
  }
});
