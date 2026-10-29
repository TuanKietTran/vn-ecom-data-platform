const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const webPort = process.env.CLIENT_WEB_PORT || "3201";
const gatewayPort = process.env.CLIENT_GATEWAY_PORT || "3202";
const baseUrl = process.env.CLIENT_WEB_URL || `http://127.0.0.1:${webPort}`;
const gatewayUrl = process.env.CLIENT_GATEWAY_URL || `http://127.0.0.1:${gatewayPort}`;
const apiUrl = process.env.PLATFORM_API_URL || `http://127.0.0.1:${process.env.CLIENT_API_PORT || "8201"}`;
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
  await page.goto(baseUrl);
  await page.getByRole("heading", { name: "Upcoming deals" }).waitFor();
  await page.getByText("No upcoming voucher windows are present", { exact: false }).waitFor();
  assert.equal(await page.locator(".home-intro").count(), 0);
  assert.equal(await page.locator("main > .chat-panel").count(), 1);
  assert.equal(await page.locator("main > .upcoming").count(), 1);
  assert.deepEqual(
    await page.locator("main > section").evaluateAll((sections) => sections.map((section) => section.className)),
    ["panel chat-panel", "panel upcoming"],
  );
  assert.equal(await page.getByRole("link", { name: "Start a hunt" }).count(), 0);
  await page.screenshot({
    path: path.join(artifacts, "web-hunt-desktop.png"),
    fullPage: true,
  });

  await page.getByRole("link", { name: "Hunt", exact: true }).click();
  await page.getByRole("heading", { name: "Find a good deal." }).waitFor();
  await page.getByLabel("Product or model").fill("Sony WH-1000XM5");
  await page.getByRole("checkbox", { name: /synthetic examples/ }).check();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const firstDeal = page.locator(".deal-card").first();
  await firstDeal.waitFor();
  await page.getByText("SYNTHETIC · DEMO", { exact: false }).first().waitFor();
  await firstDeal.locator("summary").click();
  await firstDeal.screenshot({
    path: path.join(artifacts, "web-hunt-deal.png"),
  });
  await firstDeal.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByRole("link", { name: /^Saved/ }).click();
  await page.getByText("Stored on this device only", { exact: false }).waitFor();
  await page.getByText("Saved snapshot", { exact: false }).waitFor();
  await page.reload();
  assert.equal(await page.locator(".deal-card").count(), 1);
  await page.locator(".deal-card").first().getByRole("button", { name: "Saved", exact: true }).click();
  await page.getByText("No saved deals on this device.", { exact: true }).waitFor();

  await page.getByRole("link", { name: "Home", exact: true }).click();
  await page.getByLabel("Message").fill("Compare GMV yesterday");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const assistant = page.locator(".message").filter({ has: page.locator("b", { hasText: "Hunt" }) }).last();
  await assistant.waitFor();
  assert((await assistant.innerText()).length > 10);

  await page.getByRole("link", { name: "Discover", exact: true }).click();
  await page.getByLabel("Product or model").fill("dien thoai");
  await page.getByRole("checkbox", { name: /synthetic examples/ }).check();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator(".product-row").first().waitFor();
  assert((await page.locator(".product-row").first().innerText()).includes("SYNTHETIC"));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: path.join(artifacts, "web-hunt-mobile.png"),
    fullPage: true,
  });
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  );
  const invalid = await page.request.post(`${gatewayUrl}/deals`, {
    data: { query: "" },
  });
  assert.equal(invalid.status(), 400);
  assert.deepEqual(errors, []);

  const migrationPage = await browser.newPage();
  await migrationPage.addInitScript(() => {
    localStorage.setItem(
      "shoplens.conversations.v1",
      JSON.stringify([{ id: "legacy-thread", title: "Old conversation", messages: [{ role: "user", content: "Saved history" }] }]),
    );
  });
  await migrationPage.goto(`${apiUrl}/`);
  const migrated = await migrationPage.evaluate(() => ({
    old: localStorage.getItem("shoplens.conversations.v1"),
    current: JSON.parse(localStorage.getItem("hunt.conversations.v1") || "[]"),
  }));
  assert.equal(migrated.old, null);
  assert.equal(migrated.current[0].id, "legacy-thread");
  await migrationPage.close();

  console.log(
    "PASS: 9 end-user scenario groups: Hunt home/upcoming, synthetic deal opt-in, deal save/reload/remove, data chat, discovery, mobile overflow, gateway validation, legacy chat storage migration, no page errors.",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
