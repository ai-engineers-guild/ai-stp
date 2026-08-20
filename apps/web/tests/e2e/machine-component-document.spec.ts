import { expect, test } from "@playwright/test";

const stableId = "component_01JQZK7B8N4M6P2R9T5V0X3YBE";
const humanDetail = `/en/catalog/components/${stableId}`;
const machineDetail = `/en/ai/catalog/components/${stableId}`;
const humanVersion = `${humanDetail}/versions/1.0`;
const machineVersion = `${machineDetail}/versions/1.0`;

const REQUIRED_FIELDS = [
  `stable_id: ${stableId}`,
  "version: 1.0",
  "digest: sha256:",
  "component_type: agent",
  "projection_kind: native_files",
  "harness: pi",
  "trust_lane:",
  "author_verified:",
  "component_verified:",
  "dependencies:",
  `ai-stp registry version --kind component --id ${stableId} --version 1.0`,
];

function expectCompleteDocument(text: string) {
  for (const snippet of REQUIRED_FIELDS) {
    expect(text, snippet).toContain(snippet);
  }
  expect(text).not.toMatch(/catalog-art|media_|avatar_url|csrf|youtube|session_token/i);
}

test.describe("component machine document and switch (REQ-3604, REQ-3623)", () => {
  test("keeps the exact component route after catalog navigation both ways", async ({ page }) => {
    await page.goto("/en/catalog?q=river-planner&include_experimental=1&resource=components");
    await page.getByRole("heading", { name: "river-planner-agent" }).click();
    await expect(page).toHaveURL(new RegExp(humanDetail.replaceAll("/", "\\/")));
    const machine = page.locator('[data-ui="projection-machine"]');
    await expect(machine).toHaveAttribute("href", machineDetail);
    await expect(machine).not.toHaveAttribute("href", /\/en\/ai\/catalog$/);
    await machine.click();
    await expect(page).toHaveURL(machineDetail);
    await expect(page.locator('[data-ui="machine-page-projection"]')).toBeVisible();
    expectCompleteDocument(await page.locator('[data-ui="machine-page-projection"]').innerText());
    const human = page.locator('[data-ui="projection-human"]');
    await expect(human).toHaveAttribute("href", humanDetail);
    await human.click({ force: true });
    await expect(page).toHaveURL(humanDetail);
    await expect(
      page.getByRole("heading", { level: 1, name: "river-planner-agent" }),
    ).toBeVisible();
  });

  test("preserves version, query and locale on the switch", async ({ page }) => {
    await page.goto(`${humanVersion}?include_experimental=1`);
    await expect(page.locator('[data-ui="projection-machine"]')).toHaveAttribute(
      "href",
      `${machineVersion}?include_experimental=1`,
    );
    await page.locator('[data-ui="projection-machine"]').click({ force: true });
    await expect(page).toHaveURL(`${machineVersion}?include_experimental=1`);
    const text = await page.locator('[data-ui="machine-page-projection"]').innerText();
    expectCompleteDocument(text);
    await expect(page.locator('[data-ui="projection-human"]')).toHaveAttribute(
      "href",
      `${humanVersion}?include_experimental=1`,
    );

    await page.goto(`/ru/catalog/components/${stableId}`);
    await expect(page.locator('[data-ui="projection-machine"]')).toHaveAttribute(
      "href",
      `/ru/ai/catalog/components/${stableId}`,
    );
  });

  test("keeps 404 and private-login parity on component pairs", async ({ page, request }) => {
    const missing = "component_01AAAAAAAAAAAAAAAAAAAAAAAA";
    const invalid = "component_missing";
    for (const id of [missing, invalid]) {
      expect((await request.get(`/en/catalog/components/${id}`)).status(), `human ${id}`).toBe(404);
      expect((await request.get(`/en/ai/catalog/components/${id}`)).status(), `machine ${id}`).toBe(
        404,
      );
    }
    const response = await page.goto("/en/ai/publications/plan_missing");
    expect(response?.status()).toBe(200);
    await expect(page).toHaveURL(/\/login/);
  });
});
