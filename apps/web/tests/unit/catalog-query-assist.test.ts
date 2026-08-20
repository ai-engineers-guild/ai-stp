import { describe, expect, it } from "vitest";

import {
  completeCatalogQlToken,
  correctCatalogQuery,
  suggestCatalogQlWords,
} from "@/lib/catalog-query-assist";

describe("catalog query language assist", () => {
  it("suggests reserved words from the current token", () => {
    expect(suggestCatalogQlWords("TA")).toEqual(["TAGS"]);
    expect(suggestCatalogQlWords("NAME:tool AND ")).toEqual([]);
    expect(suggestCatalogQlWords("VER")).toEqual(["VERIFIED"]);
    expect(suggestCatalogQlWords("N")).toEqual(["NAME", "NOT"]);
    expect(suggestCatalogQlWords("A")).toEqual(["AUTHOR", "AND"]);
    expect(suggestCatalogQlWords("I")).toEqual(["IN"]);
    expect(suggestCatalogQlWords("O")).toEqual(["OR"]);
    expect(suggestCatalogQlWords("H")).toEqual(["HARNESS"]);
    expect(suggestCatalogQlWords("TY")).toEqual(["TYPE"]);
  });

  it("offers simple typo corrections without rewriting already canonical words", () => {
    expect(correctCatalogQuery("harnes:codex autor:ada")).toBe("HARNESS:codex AUTHOR:ada");
    expect(correctCatalogQuery("nam:tool tipe:skill")).toBe("NAME:tool TYPE:skill");
    expect(correctCatalogQuery("NAME:tool AND TAGS:python")).toBe("NAME:tool AND TAGS:python");
    expect(correctCatalogQuery("NAME:tool and tags:python")).toBe("NAME:tool AND TAGS:python");
  });

  it("does not rewrite plain-text author, tags or verified unless they look like QL", () => {
    expect(correctCatalogQuery("author tags verified")).toBe("author tags verified");
    expect(correctCatalogQuery("search by author")).toBe("search by author");
    expect(correctCatalogQuery("NAME:author")).toBe("NAME:author");
    expect(correctCatalogQuery("harnes")).toBe("harnes");
  });

  it("replaces only the trailing token when completing", () => {
    expect(completeCatalogQlToken("NAME:tool AND TA", "TAGS")).toBe("NAME:tool AND TAGS");
  });
});
