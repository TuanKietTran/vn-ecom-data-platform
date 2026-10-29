const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const artifacts =
  process.env.CLIENT_ARTIFACT_DIR || path.resolve("artifacts/clients");
fs.mkdirSync(artifacts, { recursive: true });
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://127.0.0.1:3001");
  await page.getByText("Platform connected", { exact: true }).waitFor();
  await page.screenshot({
    path: path.join(artifacts, "web-party-desktop.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Take the demo for a spin" }).click();
  await page.locator(".deal-ticket").first().waitFor();
  await page
    .getByRole("button", { name: "Eligibility & exact variant" })
    .click();
  await page.getByLabel("Payment method", { exact: false }).fill("Demo Bank");
  await page.getByRole("spinbutton").fill("6000000");
  await page.getByRole("button", { name: "Find my deal" }).click();
  const official = page
    .locator(".deal-ticket")
    .filter({ hasText: "Demo Official" });
  await official
    .locator(".deal-price strong")
    .filter({ hasText: "5.849.000 ₫" })
    .waitFor();
  await official.locator("summary").click();
  await official.screenshot({
    path: path.join(artifacts, "web-party-receipt.png"),
  });
  await official
    .getByRole("button", { name: "Save deal", exact: true })
    .click();
  await page.getByRole("link", { name: /^Saved/ }).click();
  await page.getByText("Saved snapshot · Recheck", { exact: false }).waitFor();
  await page.reload();
  assert.equal(await page.locator(".deal-ticket").count(), 1);
  await page.getByRole("button", { name: "Remove saved deal" }).click();
  await page.getByText("Make a little room", { exact: false }).waitFor();
  await page.getByRole("link", { name: "Ask ShopLens", exact: true }).click();
  await page.getByRole("button", { name: "Compare GMV yesterday" }).click();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.locator(".chat-message.assistant").first().waitFor();
  assert(
    (await page.locator(".chat-message.assistant").innerText()).includes(
      "gold.",
    ),
  );
  assert(
    await page
      .getByRole("checkbox", { name: /Model not connected/ })
      .isDisabled(),
  );
  await page.getByRole("link", { name: "Discover", exact: true }).click();
  await page.locator(".search-input input").fill("dien thoai");
  await page.getByRole("checkbox", { name: /Include clearly labeled/ }).check();
  await page.getByRole("button", { name: "Search products" }).click();
  await page.locator(".product-row").first().waitFor();
  await page.getByRole("link", { name: "Deal hunt", exact: true }).click();
  await page.getByText("Platform connected", { exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: path.join(artifacts, "web-party-mobile.png"),
    fullPage: true,
  });
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  const invalid = await page.request.post("http://127.0.0.1:4100/deals", {
    data: { query: "" },
  });
  assert.equal(invalid.status(), 400);
  assert.deepEqual(errors, []);
  console.log(
    "PASS: gateway validation; real API deal totals/eligibility; saved persistence/removal; chat; model state; product discovery; desktop/mobile layout; no page errors.",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
