import { chromium } from "@playwright/test";

import { chromeChannel } from "./chrome-channel.ts";

const channel = chromeChannel();
const browser = await chromium.launch({ channel, headless: true });
try {
  console.log(`ensure-chrome: ${channel} ${browser.version()}`);
} finally {
  await browser.close();
}
