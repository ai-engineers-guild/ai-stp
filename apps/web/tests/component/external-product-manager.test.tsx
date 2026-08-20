import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn().mockResolvedValue({ ok: true });
const create = vi.fn().mockResolvedValue({
  ok: true,
  product: {
    schema_version: 1,
    name: "Kaspi",
    canonical_domain: "kaspi.kz",
    primary_url: "https://kaspi.kz/shop",
    country_codes: ["KZ"],
  },
});
vi.mock("@/actions/external-products", () => ({
  replaceExternalProductsAction: replace,
  createExternalProductAction: create,
}));
const { ExternalProductManager } = await import("@/components/organisms/external-product-manager");

describe("ExternalProductManager", () => {
  it("attaches existing services and creates a shallow HTTPS service", async () => {
    const user = userEvent.setup();
    render(
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
        ]}
        selectedDomains={[]}
      />,
    );
    await user.click(screen.getByRole("checkbox", { name: /Notion/ }));
    await user.click(screen.getByRole("button", { name: "Save services" }));
    expect(replace).toHaveBeenCalledWith(
      expect.objectContaining({ canonicalDomains: ["notion.so"] }),
    );
    await user.type(screen.getByRole("textbox", { name: "Service name" }), "Kaspi");
    await user.type(
      screen.getByRole("textbox", { name: "Primary HTTPS URL" }),
      "https://kaspi.kz/shop",
    );
    await user.type(screen.getByRole("textbox", { name: "Country codes" }), "KZ");
    await user.click(screen.getByRole("button", { name: "Create service" }));
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ countryCodes: ["KZ"] }));
    expect(await screen.findByText(/Service created/)).toBeVisible();
  });
});
