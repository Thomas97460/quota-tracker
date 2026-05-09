const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const outputDir = process.argv[2] || path.join(__dirname, "../assets/screenshots");

if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

const pages = [
  {
    url: "http://localhost:9000/overview",
    path: path.join(outputDir, "overview.png")
  }
];

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_BIN || "chromium",
    headless: true
  });

  for (const item of pages) {
    const page = await browser.newPage({
      viewport: { width: 1920, height: 2353 },
      deviceScaleFactor: 2
    });

    console.log(`Navigating to ${item.url}...`);
    try {
      await page.goto(item.url, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(2000); // wait for initial render

      try {
        console.log("Looking for 'all' tab...");
        const allTab = page.locator('button.range-tab:has-text("all")');
        await allTab.waitFor({ state: 'visible', timeout: 5000 });
        await allTab.click();
        console.log("Waiting for data to load (18s)...");
        await page.waitForTimeout(18000); // wait for data to load after clicking
      } catch (e) {
        console.log("Could not click 'all' tab or it was not found:", e.message);
      }

      console.log(`Saving screenshot to ${item.path}...`);
      await page.screenshot({
        path: item.path,
        fullPage: true
      });
    } catch (e) {
      console.error(`Failed to capture ${item.url}:`, e);
    } finally {
      await page.close();
    }
  }

  await browser.close();
})();
