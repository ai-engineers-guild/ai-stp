import { useState } from "react";
import { NextIntlClientProvider } from "next-intl";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import en from "../../messages/en.json";
import ru from "../../messages/ru.json";
import { MemberImportPreview } from "@/components/molecules/member-import-preview";
import { MemberImportFields } from "@/components/molecules/member-import-fields";
import { inspectMemberImport, type MemberImportRow } from "@/lib/member-import";

const rows = inspectMemberImport(
  "email,display_name\na@example.com,Alex\na@example.com,Duplicate\nbad,Bad",
);
it("shows semantic column headers, all validation results and localized empty/loading states", () => {
  const { rerender } = render(
    <NextIntlClientProvider locale="en" messages={en}>
      <MemberImportPreview rows={rows} />
    </NextIntlClientProvider>,
  );
  expect(screen.getAllByRole("columnheader")).toHaveLength(4);
  expect(screen.getByText("Duplicate email")).toBeVisible();
  expect(screen.getByText("Invalid email")).toBeVisible();
  expect(screen.getByText("Ready")).toBeVisible();
  expect(screen.getByRole("region")).toHaveAttribute("tabindex", "0");
  rerender(
    <NextIntlClientProvider locale="ru" messages={ru}>
      <MemberImportPreview rows={[]} loading />
    </NextIntlClientProvider>,
  );
  expect(screen.getByRole("region")).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("status")).toHaveTextContent("Чтение файла");
  rerender(
    <NextIntlClientProvider locale="ru" messages={ru}>
      <MemberImportPreview rows={[]} />
    </NextIntlClientProvider>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Выберите файл");
});

function Fields() {
  const [data, setData] = useState<MemberImportRow[]>([]);
  return (
    <NextIntlClientProvider locale="en" messages={en}>
      <MemberImportFields rows={data} onRows={setData} busy={false} />
    </NextIntlClientProvider>
  );
}
function csvFile(text: string, name = "members.csv") {
  const file = new File([text], name, { type: "text/csv" });
  Object.defineProperty(file, "text", { value: () => Promise.resolve(text) });
  return file;
}
it("picks a file, rejects unsupported input, and accepts a replacement by drag and drop", async () => {
  const user = userEvent.setup({ applyAccept: false });
  render(<Fields />);
  const input = screen.getByLabelText("Click to choose a file");
  await user.upload(input, csvFile("x", "members.exe"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Choose a CSV");
  await user.upload(input, csvFile("email,role,display_name\na@example.com,lead,Alex"));
  expect(await screen.findByText("Alex")).toBeVisible();
  expect(screen.queryByRole("alert")).toBeNull();
  const dropzone = input.closest("label");
  if (!dropzone) throw new Error("Missing drop target");
  fireEvent.drop(dropzone, { dataTransfer: { files: [csvFile("b@example.com,Blair")] } });
  expect(await screen.findByText("Blair")).toBeVisible();
  expect(screen.queryByText("Alex")).toBeNull();
});
it("keeps duplicate and invalid rows visible when using the paste alternative", async () => {
  const user = userEvent.setup();
  render(<Fields />);
  await user.click(screen.getByText("Or paste a list", { selector: "summary" }));
  await user.type(
    screen.getByLabelText("Or paste a list"),
    "a@example.com,Alex\na@example.com,Again\nbad,Invalid",
  );
  expect(screen.getByText("Duplicate email")).toBeVisible();
  expect(screen.getByText("Invalid email")).toBeVisible();
  expect(screen.getByText(/2 rows skipped/)).toBeVisible();
});
