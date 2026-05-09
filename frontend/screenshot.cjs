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
      viewport: { width: 1920, height: 3000 },
      deviceScaleFactor: 2
    });

    console.log(`Navigating to ${item.url}...`);
    try {
      await page.goto(item.url, { waitUntil: "networkidle" });
      
      // Inject CSS to disable animations, increase font sizes, and add a gradient border
      await page.addStyleTag({
        content: `
          *, *::before, *::after {
            animation: none !important;
            transition: none !important;
          }
          
          /* Revert titles to normal-ish and boost small text only */
          html {
            font-size: 19px !important;
            background: linear-gradient(135deg, #8B5CF6, #4F8DF7, #F59E0B) !important;
            padding: 10px !important;
            box-sizing: border-box !important;
            height: auto !important;
          }
          
          body {
            border-radius: 12px !important;
            overflow: hidden !important;
            background: #0A0B10 !important; /* Force background-0 color */
            position: relative !important;
          }
          
          .page-title { font-size: 30px !important; }
          .kpi-value { font-size: 38px !important; }
          .card-title { font-size: 24px !important; }
          
          /* Boost the small texts specifically - back to very readable sizes */
          .page-sub, .card-sub, .kpi-label, .kpi-foot, .sidebar-brand-sub, 
          .nav-provider-pct, .quota-card-sub, .quota-meta, .meta-stat-label,
          .crumb-status, .crumb-title, .tag, .mono, .tabular, .dim, .dim span {
            font-size: 22px !important;
            font-weight: 500 !important;
          }
          
          .table thead th { font-size: 19px !important; letter-spacing: 0 !important; }
          .table tbody td { font-size: 22px !important; }
          
          /* Targeting Recharts specifically for chart labels/ticks */
          /* Keeping these smaller as requested to avoid overflow */
          .recharts-cartesian-axis-tick text {
            font-size: 15px !important; 
            font-weight: 600 !important;
          }
          
          /* Give more room to the Y axis to avoid overflow */
          .recharts-cartesian-axis.recharts-y-axis {
            transform: translateX(-5px) !important;
          }

          .recharts-legend-item-text {
            font-size: 19px !important;
          }
          .recharts-default-tooltip {
            font-size: 19px !important;
          }
        `
      });

      await page.waitForTimeout(3000); 

      try {
        console.log("Ensuring data fetch by clicking '7d' then 'all'...");
        const tab7d = page.locator('.topbar button.range-tab:has-text("7d")');
        const allTab = page.locator('.topbar button.range-tab:has-text("all")');
        
        await tab7d.click();
        await page.waitForTimeout(2000);
        await allTab.click();
        
        console.log("Waiting for data and rendering (20s)...");
        await page.waitForTimeout(20000);
        
        // Trigger resize to help Recharts ResponsiveContainer
        await page.evaluate(() => {
          window.dispatchEvent(new Event('resize'));
        });
        await page.waitForTimeout(2000);

        // Scroll to trigger any lazy rendering
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.waitForTimeout(2000);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.waitForTimeout(2000);

        const curves = await page.locator('path.recharts-curve').count();
        const areas = await page.locator('path.recharts-area').count();
        console.log(`Found ${curves} curves and ${areas} areas.`);

      } catch (e) {
        console.log("Error during interaction:", e.message);
      }

      console.log(`Saving screenshot to ${item.path}...`);
      await page.screenshot({
        path: item.path,
        fullPage: false // Use fixed viewport to avoid Recharts resizing issues
      });
    } catch (e) {
      console.error(`Failed to capture ${item.url}:`, e);
    } finally {
      await page.close();
    }
  }

  await browser.close();
})();
