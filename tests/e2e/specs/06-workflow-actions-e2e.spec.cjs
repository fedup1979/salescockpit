const { test, expect } = require("playwright/test");
const { hasCredentials, loginAs, missingCredentialsMessage } = require("../fixtures/auth.cjs");
const { clickFirstVisible, openInboxConversation } = require("../helpers/navigation.cjs");

async function assertMockMode(page) {
  const response = await page.request.get("http://139.59.158.77:8602/health");
  const json = await response.json();
  expect(json.mode).toBe("mock");
}

test.describe("P6 workflow actions on demo prospects", () => {
  test("setter I can send a freeform reply in mock mode", async ({ page }) => {
    test.skip(!hasCredentials("setter1"), missingCredentialsMessage("setter1"));
    test.skip(process.env.SC_E2E_ALLOW_MUTATION !== "true", "Set SC_E2E_ALLOW_MUTATION=true to run mutating E2E tests");
    await assertMockMode(page);

    await loginAs(page, "setter1");
    await openInboxConversation(page, "Léa Martin");
    await expect(page.getByText("Fenêtre WhatsApp ouverte", { exact: false }).first()).toBeVisible();
    await page.getByLabel("Message libre").fill("Bonjour, merci pour votre message. Test Playwright staging.");
    await page.getByRole("button", { name: "Envoyer le message libre" }).click();
    await expect(page.locator("body")).toContainText("Test Playwright staging");
  });

  test("do-not-contact inbound review can be lifted into a reply action", async ({ page }) => {
    test.skip(!hasCredentials("setter1"), missingCredentialsMessage("setter1"));
    test.skip(process.env.SC_E2E_ALLOW_MUTATION !== "true", "Set SC_E2E_ALLOW_MUTATION=true to run mutating E2E tests");

    await loginAs(page, "setter1");
    await openInboxConversation(page, "Hugo Muller");
    await expect(page.getByText("Ne plus contacter", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Contact bloqué", { exact: false }).first()).toBeVisible();
    await page.getByRole("tab", { name: "Actions" }).click();
    await page.getByLabel("Note de revue").fill("Le prospect a réécrit, reprise autorisée par test Playwright.");
    await page.getByRole("button", { name: "Lever et répondre" }).click();
    await expect(page.getByText("Contact autorisé", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Répondre au message", { exact: false }).first()).toBeVisible();
  });

  test("setter II can skip a skippable follow-up and see the next flow consequence", async ({ page }) => {
    test.skip(!hasCredentials("setter2"), missingCredentialsMessage("setter2"));
    test.skip(process.env.SC_E2E_ALLOW_MUTATION !== "true", "Set SC_E2E_ALLOW_MUTATION=true to run mutating E2E tests");

    await loginAs(page, "setter2");
    await openInboxConversation(page, "Sarah Perrin");
    await expect(page.locator("body")).toContainText("Relancer Sarah Perrin");
    await clickFirstVisible(page.getByRole("button", { name: /^X$/ }));
    await expect(page.locator("body")).toContainText("Attention danger");
    await page.getByLabel("Note obligatoire").last().fill("Relance ignorée par test Playwright.");
    await clickFirstVisible(page.getByText("Je confirme que cette étape de flux doit être ignorée.", { exact: true }));
    await page.getByRole("button", { name: "Ignorer cette étape" }).click();
    await expect(page.locator("body")).toContainText("Étape ignorée");
  });
});
