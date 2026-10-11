import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { InfoNote } from "@/components/molecules/info-note";
import { SettingsSection } from "@/components/molecules/settings-section";
import { SwitchRow } from "@/components/molecules/switch-row";

describe("SwitchRow", () => {
  it("submits the boolean contract through the hidden input", () => {
    const { container } = render(
      <form>
        <SwitchRow id="hb" name="heartbeat_enabled" label="Heartbeat" value disabled={false} />
      </form>,
    );
    const hidden = container.querySelector<HTMLInputElement>('input[name="heartbeat_enabled"]');
    expect(hidden?.value).toBe("true");
  });

  it("swaps the status text when the control is toggled", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <SwitchRow
        id="hb"
        name="heartbeat_enabled"
        label="Device heartbeat"
        value
        disabled={false}
        status={{ on: "Enabled", off: "Disabled", onHint: "Reporting is active." }}
      />,
    );
    expect(screen.getByText("Enabled")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Device heartbeat" }));
    expect(screen.getByText("Disabled")).toBeInTheDocument();
    expect(
      container.querySelector<HTMLInputElement>('input[name="heartbeat_enabled"]')?.value,
    ).toBe("false");
  });
});

describe("InfoNote", () => {
  it("renders explanatory text without alert semantics", () => {
    render(<InfoNote>Only technical data is collected.</InfoNote>);
    expect(screen.getByText("Only technical data is collected.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("SettingsSection", () => {
  it("renders title, description, aside and body", () => {
    render(
      <SettingsSection
        icon="activity"
        title="Device heartbeat"
        description="Control reporting."
        aside={<span>aside-slot</span>}
      >
        <p>body</p>
      </SettingsSection>,
    );
    expect(screen.getByRole("heading", { name: "Device heartbeat" })).toBeInTheDocument();
    expect(screen.getByText("Control reporting.")).toBeInTheDocument();
    expect(screen.getByText("aside-slot")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });

  it("lets a composite header replace the default one", () => {
    render(
      <SettingsSection header={<h3>custom header</h3>}>
        <p>body</p>
      </SettingsSection>,
    );
    expect(screen.getByRole("heading", { name: "custom header" })).toBeInTheDocument();
  });
});
