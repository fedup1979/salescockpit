const { test, expect } = require("playwright/test");
const { hasCredentials, loginAs, missingCredentialsMessage } = require("../fixtures/auth.cjs");
const { clickFirstVisible, openNav } = require("../helpers/navigation.cjs");

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function expectDomContains(page, text) {
  await expect.poll(async () => page.getByText(text, { exact: false }).count()).toBeGreaterThan(0);
}

test.describe("P5 admin bug workflow", () => {
  test("bug report creates an admin action and can be marked resolved", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));
    test.skip(process.env.SC_E2E_ALLOW_MUTATION !== "true", "Set SC_E2E_ALLOW_MUTATION=true to run mutating E2E tests");

    const title = `Test fonction bug Playwright ${Date.now()}`;
    await loginAs(page, "admin");

    await page.getByRole("button", { name: "Bug" }).click();
    await expect(page.getByText("Signaler un bug")).toBeVisible();
    await page.getByLabel("Titre court").fill(title);
    await page.getByLabel("Ce qui semble incorrect ou améliorable").fill("démo playwright");
    await page.getByLabel("Ce que vous voyez").fill("démo");
    await page.getByLabel("Ce que vous attendiez").fill("démo");
    await page.getByTestId("stDialog").getByRole("button", { name: "Envoyer" }).click();
    await expect(page.getByText("Signalement enregistré", { exact: false })).toBeVisible();

    await openNav(page, "Admin");
    await page.getByRole("tab", { name: "Signalements" }).click();
    await expectDomContains(page, title);
    await expectDomContains(page, "open");

    await page.getByRole("tab", { name: "Actions admin" }).click();
    await page.getByRole("combobox", { name: /Action.*terminer/i }).click();
    await page.getByRole("list").last().hover();
    for (let attempt = 0; attempt < 8 && (await page.getByText(title, { exact: false }).count()) === 0; attempt += 1) {
      await page.mouse.wheel(0, 700);
      await page.waitForTimeout(200);
    }
    await expectDomContains(page, title);
    await clickFirstVisible(page.getByText(new RegExp(escapeRegex(title), "i")));
    await page.getByLabel("Résolution").fill("traité par Playwright");
    await page.getByRole("button", { name: "Marquer terminée" }).click();
    await page.waitForTimeout(1200);

    await page.getByRole("tab", { name: "Actions admin" }).click();
    await page.getByRole("combobox", { name: /Action.*terminer/i }).click();
    await page.getByRole("list").last().hover();
    for (let attempt = 0; attempt < 8 && (await page.getByText(title, { exact: false }).count()) > 0; attempt += 1) {
      await page.mouse.wheel(0, 700);
      await page.waitForTimeout(200);
    }
    await expect(page.getByText(title, { exact: false })).toHaveCount(0);

    await page.getByRole("tab", { name: "Signalements" }).click();
    await expectDomContains(page, title);
  });
});
