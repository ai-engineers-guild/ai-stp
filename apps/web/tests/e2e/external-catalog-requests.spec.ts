import { expect, test } from "@playwright/test";

const stableId = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z";

test.describe("external catalog requests", () => {
  test("owner submits a service and a localized country request from the editor", async ({
    page,
  }) => {
    await page.goto("/en/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/en\/account/, { timeout: 30_000 });

    await page.goto(`/en/objects/component/${stableId}/edit`);
    await expect(page.getByRole("heading", { name: "Linked service" })).toBeVisible();
    await expect(page.locator("main h2")).toHaveText(["Catalog bio", "Linked service", "Media"]);

    await page.getByRole("button", { name: "Add a new service" }).click();
    const serviceDialog = page.getByRole("dialog", { name: "Request a new service" });
    await serviceDialog.getByRole("textbox", { name: /Service name/ }).fill("Example Service");
    await serviceDialog
      .getByRole("textbox", { name: /Primary HTTPS URL/ })
      .fill("https://example.com/docs");
    await serviceDialog
      .getByRole("textbox", { name: /Russian description/ })
      .fill("Описание сервиса");
    await serviceDialog
      .getByRole("textbox", { name: /English description/ })
      .fill("Service description");
    await serviceDialog
      .getByRole("textbox", { name: /Description source HTTPS URL/ })
      .fill("https://example.com/about");
    await serviceDialog.getByRole("button", { name: "Add a new country" }).click();
    const countryDialog = page.getByRole("dialog", { name: "Request a new country" });
    await countryDialog.getByRole("textbox", { name: /ISO country code/ }).fill("KZ");
    await countryDialog.getByRole("textbox", { name: /Russian country name/ }).fill("Казахстан");
    await countryDialog.getByRole("textbox", { name: /English country name/ }).fill("Kazakhstan");
    await countryDialog.getByRole("button", { name: "Submit country request" }).click();
    await expect(serviceDialog.getByRole("status")).toContainText("Country request submitted");

    await serviceDialog.getByRole("button", { name: "Submit service request" }).click();
    await expect(serviceDialog.getByRole("status")).toContainText("Service request submitted");
  });
});
