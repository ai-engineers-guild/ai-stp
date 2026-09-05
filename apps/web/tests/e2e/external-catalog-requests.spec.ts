import { expect, test } from "@playwright/test";

const stableId = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z";

test.describe("external catalog requests", () => {
  test("owner submits a service without countries and a localized country request", async ({
    page,
  }) => {
    await page.goto("/en/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/en\/account/, { timeout: 30_000 });

    await page.goto(`/en/objects/component/${stableId}`);
    await expect(page.getByRole("heading", { name: "External services" })).toBeVisible();

    await page.getByRole("textbox", { name: "Service name" }).fill("Example Service");
    await page.getByRole("textbox", { name: "Primary HTTPS URL" }).fill("https://example.com/docs");
    await page.getByRole("textbox", { name: "Russian description" }).fill("Описание сервиса");
    await page.getByRole("textbox", { name: "English description" }).fill("Service description");
    await page
      .getByRole("textbox", { name: "Description source HTTPS URL" })
      .fill("https://example.com/about");
    await page.getByRole("button", { name: "Request service" }).click();
    await expect(page.getByRole("status")).toContainText("Service request submitted");

    await page.getByRole("textbox", { name: "ISO country code" }).fill("KZ");
    await page.getByRole("textbox", { name: "Russian country name" }).fill("Казахстан");
    await page.getByRole("textbox", { name: "English country name" }).fill("Kazakhstan");
    await page.getByRole("button", { name: "Request country" }).click();
    await expect(page.getByRole("status")).toContainText("Country request submitted");
  });
});
