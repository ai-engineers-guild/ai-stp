import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { SsoSignIn } from "@/components/molecules/sso-sign-in";

const authentik = { label: "Continue with authentik", href: "/v1/auth/authentik/login" };
const keycloak = { label: "Continue with Keycloak", href: "/v1/auth/keycloak/login" };

describe("SsoSignIn", () => {
  it("renders nothing without providers", () => {
    const { container } = render(<SsoSignIn label="Continue with SSO" options={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("links straight to the provider when exactly one is configured", () => {
    render(<SsoSignIn label="Continue with SSO" options={[keycloak]} />);
    const link = screen.getByRole("link", { name: "Continue with SSO" });
    expect(link).toHaveAttribute("href", "/v1/auth/keycloak/login");
  });

  it("opens a chooser when several providers are configured", async () => {
    const user = userEvent.setup();
    render(<SsoSignIn label="Continue with SSO" options={[authentik, keycloak]} />);

    const trigger = screen.getByRole("button", { name: "Continue with SSO" });
    expect(trigger).toBeInTheDocument();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await user.click(trigger);
    const links = await screen.findAllByRole("menuitem");
    expect(links.map((node) => node.textContent)).toEqual([
      "Continue with authentik",
      "Continue with Keycloak",
    ]);
    expect(links[0]).toHaveAttribute("href", "/v1/auth/authentik/login");
    expect(links[1]).toHaveAttribute("href", "/v1/auth/keycloak/login");
  });
});
