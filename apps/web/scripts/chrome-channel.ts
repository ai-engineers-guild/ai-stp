export function chromeChannel(): "chrome" | "chrome-beta" {
  const channel = process.env.PLAYWRIGHT_CHROME_CHANNEL ?? "chrome";
  if (channel !== "chrome" && channel !== "chrome-beta") {
    throw new Error("PLAYWRIGHT_CHROME_CHANNEL must be chrome or chrome-beta");
  }
  return channel;
}
