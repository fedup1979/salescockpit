const { test, expect } = require("playwright/test");
const { hasCredentials, loginAs, missingCredentialsMessage } = require("../fixtures/auth.cjs");
const {
  clickFirstVisible,
  openInboxConversation,
  openNav,
} = require("../helpers/navigation.cjs");

test.describe("P8 deeper operational workflows", () => {
  test("closer can document a due closing call as signed", async ({ page }) => {
    test.skip(!hasCredentials("closer"), missingCredentialsMessage("closer"));
    test.skip(process.env.SC_E2E_ALLOW_MUTATION !== "true", "Set SC_E2E_ALLOW_MUTATION=true to run mutating E2E tests");

    await loginAs(page, "closer");
    await openInboxConversation(page, "Nicolas Meyer");
    await expect(page.locator("body")).toContainText("Appeler et documenter l'appel closing de Nicolas Meyer");
    await page.getByRole("tab", { name: "Actions" }).click();
    await page.getByLabel("Note d'appel obligatoire").fill("Closing signé par test Playwright.");
    await page.getByRole("button", { name: "Enregistrer le résultat" }).click();
    await expect(page.locator("body")).toContainText("A signé");
  });

  test("admin can reactivate a completed conversation", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));
    test.skip(process.env.SC_E2E_ALLOW_MUTATION !== "true", "Set SC_E2E_ALLOW_MUTATION=true to run mutating E2E tests");

    await loginAs(page, "admin");
    await openInboxConversation(page, "Schmid", "Chloé Schmid");
    await clickFirstVisible(page.getByRole("button", { name: "Réactiver" }));
    const reason = page.getByLabel("Raison de réactivation");
    await reason.fill("Réactivation test Playwright.");
    await reason.press("Tab");
    await page.waitForTimeout(900);
    await page.getByRole("button", { name: "Réactiver" }).last().click({ force: true });
    await expect(page.getByRole("button", { name: "Clore la conversation" }).first()).toBeVisible();
  });

  test("setter II can create a template request without linking a Twilio template", async ({ page }) => {
    test.skip(!hasCredentials("setter2"), missingCredentialsMessage("setter2"));
    test.skip(process.env.SC_E2E_ALLOW_MUTATION !== "true", "Set SC_E2E_ALLOW_MUTATION=true to run mutating E2E tests");

    await loginAs(page, "setter2");
    await openInboxConversation(page, "Thomas Girard");
    await expect(page.locator("body")).toContainText("Modèle manquant");
    await page.getByLabel("Modèle manquant").fill("Modèle financement employeur Playwright");
    await page.getByLabel("Contexte pour le modèle").fill("Le prospect demande si l'employeur peut prendre en charge la formation.");
    await page.getByRole("button", { name: "Créer la demande de modèle" }).click();
    await expect(page.locator("body")).toContainText(/Demande.*modèle|demande.*modèle/i);

    await openNav(page, "Modèles");
    await expect(page.locator("body")).toContainText("Demandes de modèles à créer");
    await expect(page.locator("body")).toContainText("to_create");
  });

  test("setter I can complete a manual reprise with a mandatory note", async ({ page }) => {
    test.skip(!hasCredentials("setter1"), missingCredentialsMessage("setter1"));
    test.skip(process.env.SC_E2E_ALLOW_MUTATION !== "true", "Set SC_E2E_ALLOW_MUTATION=true to run mutating E2E tests");

    await loginAs(page, "setter1");
    await openInboxConversation(page, "Sonia Mercier");
    await expect(page.locator("body")).toContainText("Reprise manuelle setter de Sonia Mercier");
    await page.getByRole("tab", { name: "Actions" }).click();
    await page.getByLabel("Note obligatoire").last().fill("Reprise setter terminée par test Playwright.");
    await page.getByRole("button", { name: "Marquer la reprise terminée" }).click();
    await expect(page.locator("body")).toContainText(/terminée|Étape ignorée|Action suivante/i);
  });
});
