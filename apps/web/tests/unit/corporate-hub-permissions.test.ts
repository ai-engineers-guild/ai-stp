import { expect, it } from "vitest";
import { canViewCorporateAdministration, canViewCorporateSection } from "@/lib/corporate-hub";

it("keeps operational team/project rights separate from administration", () => {
  const capabilities = [
    "member.list",
    "team.list",
    "team.update",
    "project.list",
    "project.update",
  ];
  expect(canViewCorporateAdministration(capabilities)).toBe(false);
  expect(canViewCorporateSection("admins", capabilities)).toBe(false);
  expect(canViewCorporateSection("teams", capabilities)).toBe(true);
  expect(canViewCorporateSection("technologies", capabilities)).toBe(false);
  expect(canViewCorporateSection("unknown", capabilities)).toBe(false);
});

it("shows administration for each supported administrative area", () => {
  for (const permission of [
    "role.list",
    "binding.list",
    "service_principal.list",
    "audit.list",
    "job_title.list",
    "landscape.manage",
    "member.update",
    "member.delete",
  ])
    expect(canViewCorporateAdministration([permission])).toBe(true);
  expect(canViewCorporateAdministration([])).toBe(false);
});
