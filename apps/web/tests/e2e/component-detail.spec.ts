import { expect, test } from "@playwright/test";

const stableId = "component_01JQZK7B8N4M6P2R9T5V0X3YBE";

test.describe("component detail actions and media (SPEC-035)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/en/catalog/components/${stableId}`);
    await expect(
      page.getByRole("heading", { level: 1, name: "river-planner-agent" }),
    ).toBeVisible();
  });

  test("exposes source, author, history, copy, like and report actions", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await expect(page.getByRole("link", { name: "View source on GitHub" })).toHaveAttribute(
      "href",
      "https://github.com/ai-stp-examples/river-planner-agent/tree/6f1b0f5f7f3f4f2a1c9d8e7b6a5f4e3d2c1b0a99/components/river-planner-agent",
    );
    await expect(page.getByRole("heading", { name: "Author" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Version history/ })).toBeVisible();
    await expect(page.locator('[data-component-type="agent"]')).toBeVisible();
    await expect(page.locator('header img[src*="/catalog-art/agent"]')).toHaveCount(0);

    await expect(page.locator('[data-ui="component-overflow"]')).toHaveClass(/top-0/);
    await expect(page.locator('[data-ui="component-overflow"]')).toHaveClass(/right-0/);
    await expect(page.getByText("View exact source")).toHaveCount(0);
    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByRole("menuitem", { name: "Copy ID" }).click();
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(stableId);

    await page.getByRole("button", { name: "Like · 0" }).click();
    await expect(page.getByRole("button", { name: "Liked · 1" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByRole("menuitem", { name: "Report component" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.locator('input[name="subject"]')).toHaveValue(new RegExp(stableId));

    await page.goto("/en/catalog?include_experimental=1&resource=components");
    const catalogCard = page
      .getByRole("heading", { name: "river-planner-agent" })
      .locator("xpath=ancestor::article");
    await expect(catalogCard.locator('[data-component-type="agent"]')).toBeVisible();
  });

  test("opens a prefilled contact report without requiring sign in", async ({ page }) => {
    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByRole("menuitem", { name: "Report component" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.locator('input[name="subject"]')).toHaveValue(new RegExp(stableId));
  });

  test("opens and closes the primary media popup", async ({ page }) => {
    const preview = page.getByRole("button", { name: /Open media: river-planner-agent preview/i });
    await expect(preview).toBeVisible();
    await preview.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "Close media" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test("keeps EN/RU parity and a quiet console", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => {
      errors.push(error.message);
    });
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    await page.goto(`/ru/catalog/components/${stableId}`);
    await expect(
      page.getByRole("heading", { level: 1, name: "river-planner-agent" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: "\u0414\u0440\u0443\u0433\u0438\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /\u041d\u0440\u0430\u0432\u0438\u0442\u0441\u044f/ }),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
});
