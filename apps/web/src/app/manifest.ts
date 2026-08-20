import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ai_stp — setup passports",
    short_name: "ai_stp",
    description: "Passports, trust lines and safe lifecycle for AI coding harness setups.",
    start_url: "/",
    display: "standalone",
    // Manifest colors cannot reference runtime CSS variables; mirrors tokens.json machine canvas.
    // eslint-disable-next-line no-restricted-syntax
    background_color: "#101010",
    // eslint-disable-next-line no-restricted-syntax
    theme_color: "#101010",
    icons: [
      { src: "/brand/favicon-32.png", sizes: "32x32", type: "image/png" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
