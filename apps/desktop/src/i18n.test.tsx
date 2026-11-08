// @vitest-environment jsdom
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import LanguageSelect from "./components/LanguageSelect";
import {
  changeLocale,
  formatDateTime,
  formatNumber,
  i18n,
  languages,
  matchLocale,
  preferredLocale,
  useLocale,
  useText,
  type Locale,
} from "./i18n";

afterEach(async () => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  await changeLocale("en", false);
});

it.each([
  [["ru-KZ"], "ru"],
  [["kk-KZ"], "kk"],
  [["ar-SA"], "ar"],
  [["zh-CN"], "zh-Hans"],
  [["zh-SG"], "zh-Hans"],
  [["zh-Hans-HK"], "zh-Hans"],
  [["zh-Hant", "ru-RU"], "ru"],
  [["kk-Latn", "ar-EG"], "ar"],
  [["invalid_tag", "de-DE", "en-GB"], "en"],
  [[], "en"],
])("matches a supported script in %j", (preferences, expected) => {
  expect(matchLocale(preferences as string[])).toBe(expected);
});

it("uses a saved language before the platform's preferences", () => {
  vi.stubGlobal("navigator", { languages: ["ar-SA"] });
  localStorage.setItem("ai-stp.locale", "kk");
  expect(preferredLocale()).toBe("kk");
  localStorage.setItem("ai-stp.locale", "not-supported");
  expect(preferredLocale()).toBe("ar");
});

it("keeps the latest requested language and its direction and preference", async () => {
  const requests = ["ru", "ar", "kk", "zh-Hans"] as const;
  const results = await Promise.all(
    requests.map((locale) => changeLocale(locale)),
  );
  expect(results.at(-1)).toBe(true);
  expect(i18n.resolvedLanguage).toBe("zh-Hans");
  expect(useLocale.getState()).toEqual({
    locale: "zh-Hans",
    pending: false,
    failed: false,
  });
  expect(document.documentElement.dir).toBe("ltr");
  expect(localStorage.getItem("ai-stp.locale")).toBe("zh-Hans");
});

it("switches packaged catalogs without remounting entered text or the language control", async () => {
  function Form() {
    const text = useText();
    const [value, setValue] = useState("");
    return (
      <>
        <LanguageSelect />
        <label>
          {text("installInput.setupId")}
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
      </>
    );
  }
  render(<Form />);
  const input = screen.getByRole("textbox");
  const select = screen.getByRole("combobox");
  fireEvent.change(input, { target: { value: "setup_тест_بداية_测试" } });
  for (const locale of Object.keys(languages) as Locale[]) {
    await act(async () => {
      await changeLocale(locale);
    });
    expect(screen.getByRole("textbox")).toBe(input);
    expect((input as HTMLInputElement).value).toBe("setup_тест_بداية_测试");
    expect(screen.getByRole("combobox")).toBe(select);
    expect((select as HTMLSelectElement).value).toBe(locale);
    expect(document.documentElement.lang).toBe(locale);
    expect(document.documentElement.dir).toBe(languages[locale].direction);
    expect(screen.getByRole("option", { name: "Қазақша · KZ" })).toHaveProperty(
      "value",
      "kk",
    );
  }
});

it("changes the current language even when preference storage is denied", async () => {
  vi.stubGlobal("localStorage", {
    getItem() {
      throw new Error("Storage denied");
    },
    setItem() {
      throw new Error("Storage denied");
    },
  });
  expect(await changeLocale("ar")).toBe(true);
  expect(document.documentElement.dir).toBe("rtl");
  expect(useLocale.getState().failed).toBe(false);
  expect(formatNumber(1234)).toBe(new Intl.NumberFormat("ar").format(1234));
  expect(formatDateTime("not-a-date")).toBe("not-a-date");
});
