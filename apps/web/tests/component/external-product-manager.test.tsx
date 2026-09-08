import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../messages/en.json";

const replace = vi.fn();
const requestService = vi.fn();
const requestCountry = vi.fn();
vi.mock("@/actions/external-products", () => ({
  replaceExternalProductsAction: replace,
  requestExternalProductAction: requestService,
  requestCountryAction: requestCountry,
}));
const { ExternalProductManager } = await import("@/components/organisms/external-product-manager");

function renderManager(selectedDomains: string[] = ["notion.so"]) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <ExternalProductManager
        locale="en"
        objectKind="component"
        stableId="component_12345678"
        csrfToken="csrf"
        initialProducts={[
          {
            schema_version: 1,
            name: "Notion",
            canonical_domain: "notion.so",
            primary_url: "https://notion.so",
            country_codes: ["US"],
          },
          {
            schema_version: 1,
            name: "Kaspi",
            canonical_domain: "kaspi.kz",
            primary_url: "https://kaspi.kz",
            country_codes: ["KZ"],
          },
        ]}
        selectedDomains={selectedDomains}
      />
    </NextIntlClientProvider>,
  );
}

async function openServiceDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Add a new service" }));
  return screen.getByRole("dialog", { name: "Request a new service" });
}

describe("ExternalProductManager", () => {
  beforeEach(() => {
    replace.mockReset().mockResolvedValue({ ok: true });
    requestService.mockReset().mockResolvedValue({ ok: true, caseId: "report_service" });
    requestCountry.mockReset().mockResolvedValue({ ok: true, caseId: "report_country" });
  });

  it("shows the initial service, searches by name, and saves one relation", async () => {
    const user = userEvent.setup();
    renderManager();

    expect(screen.getByText("Notion · notion.so")).toBeVisible();
    await user.click(screen.getByText("Notion · notion.so"));
    await user.type(screen.getByRole("searchbox", { name: "Search services by name" }), "Kaspi");
    await user.click(screen.getByRole("radio", { name: /Kaspi/ }));
    await user.click(screen.getByRole("button", { name: "Save service link" }));

    expect(replace).toHaveBeenCalledWith(
      expect.objectContaining({ canonicalDomains: ["kaspi.kz"] }),
    );
  });

  it("requests a service and a country from nested dialogs", async () => {
    const user = userEvent.setup();
    renderManager([]);
    const dialog = await openServiceDialog(user);

    await user.type(
      within(dialog).getByRole("textbox", { name: /Service name/ }),
      "Example Service",
    );
    await user.type(
      within(dialog).getByRole("textbox", { name: /Primary HTTPS URL/ }),
      "https://example.com/docs",
    );
    await user.type(
      within(dialog).getByRole("textbox", { name: /Russian description/ }),
      "Описание",
    );
    await user.type(
      within(dialog).getByRole("textbox", { name: /English description/ }),
      "Description",
    );
    await user.type(
      within(dialog).getByRole("textbox", { name: /Description source HTTPS URL/ }),
      "https://example.com/about",
    );

    await user.click(within(dialog).getByRole("button", { name: "Add a new country" }));
    const countryDialog = screen.getByRole("dialog", { name: "Request a new country" });
    await user.type(within(countryDialog).getByRole("textbox", { name: /ISO country code/ }), "KZ");
    await user.type(
      within(countryDialog).getByRole("textbox", { name: /Russian country name/ }),
      "Казахстан",
    );
    await user.type(
      within(countryDialog).getByRole("textbox", { name: /English country name/ }),
      "Kazakhstan",
    );
    await user.click(within(countryDialog).getByRole("button", { name: "Submit country request" }));

    expect(requestCountry).toHaveBeenCalledWith(expect.objectContaining({ code: "KZ" }));
    expect(within(dialog).getByRole("textbox", { name: /Country codes/ })).toHaveValue("KZ");
    await user.click(within(dialog).getByRole("button", { name: "Submit service request" }));

    expect(requestService).toHaveBeenCalledWith(expect.objectContaining({ countryCodes: ["KZ"] }));
    expect(await within(dialog).findByText(/Service request submitted/)).toBeVisible();
  });

  it("keeps request values after a server error and rejects an invalid country code", async () => {
    const user = userEvent.setup();
    requestService.mockResolvedValueOnce({ ok: false, message: "service domain already exists" });
    renderManager([]);
    const dialog = await openServiceDialog(user);

    const name = within(dialog).getByRole("textbox", { name: /Service name/ });
    await user.type(name, "Existing Service");
    await user.type(
      within(dialog).getByRole("textbox", { name: /Primary HTTPS URL/ }),
      "https://existing.example",
    );
    await user.type(
      within(dialog).getByRole("textbox", { name: /Russian description/ }),
      "Описание",
    );
    await user.type(
      within(dialog).getByRole("textbox", { name: /English description/ }),
      "Description",
    );
    await user.type(
      within(dialog).getByRole("textbox", { name: /Description source HTTPS URL/ }),
      "https://existing.example/about",
    );
    await user.click(within(dialog).getByRole("button", { name: "Submit service request" }));

    expect(await within(dialog).findByText("service domain already exists")).toBeVisible();
    expect(name).toHaveValue("Existing Service");

    await user.click(within(dialog).getByRole("button", { name: "Add a new country" }));
    const countryDialog = screen.getByRole("dialog", { name: "Request a new country" });
    await user.type(within(countryDialog).getByRole("textbox", { name: /ISO country code/ }), "K");
    await user.click(within(countryDialog).getByRole("button", { name: "Submit country request" }));
    expect(
      await within(countryDialog).findByText("Enter a two-letter country code."),
    ).toBeVisible();
  });
});
