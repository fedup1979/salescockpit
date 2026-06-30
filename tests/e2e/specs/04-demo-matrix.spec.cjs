const { test, expect } = require("playwright/test");
const { hasCredentials, loginAs, missingCredentialsMessage } = require("../fixtures/auth.cjs");
const { openInboxConversation, searchInbox } = require("../helpers/navigation.cjs");

const demoCases = [
  ["Léa Martin", ["Répondre à Léa Martin", "Client attend"]],
  ["Marc Dubois", ["Relancer Marc Dubois"]],
  ["Sarah Perrin", ["Relancer Sarah Perrin"]],
  ["Aline Favre", ["Relancer Aline Favre"]],
  ["Thomas Girard", ["Relancer Thomas Girard"]],
  ["Nadia Keller", ["Appeler et documenter l'appel setting de Nadia Keller"]],
  ["Romain Blanc", ["rappel setting de Romain Blanc"]],
  ["Nicolas Meyer", ["Appeler et documenter l'appel closing de Nicolas Meyer"]],
  ["Morel", ["rappel closing d'Émilie Morel"]],
  ["Mathieu Garnier", ["Relancer Mathieu Garnier", "Va signer"]],
  ["Océane Petit", ["avant début de cours"]],
  ["Hugo Muller", ["Revoir le statut de contact de Hugo Muller", "Ne plus contacter"]],
  ["Irina Lopes", ["A signé"]],
  ["Chloé Schmid", ["Chloé Schmid"]],
  ["Philippe Aubert", ["Non pertinent"]],
  ["4016", ["Inconnu(e)", "Répondre à Inconnu(e)"]],
  ["Laura Admin Démo", ["Valider le wording du modèle financement"]],
  ["François Admin Démo", ["Relire la logique de transitions"]],
  ["Tiago Admin Démo", ["Vérifier le mapping SchoolDrive"]],
  ["Camille Laurent", ["Relancer Camille Laurent"]],
  ["Luc Moreau", ["Appeler et documenter l'appel setting de Luc Moreau"]],
  ["Sonia Mercier", ["Reprise manuelle setter de Sonia Mercier"]],
  ["Yves Caron", ["Reprise manuelle closer de Yves Caron"]],
  ["Emma Complet", ["complète"]],
  ["Rita Roadmap", ["Roadmap"]],
];

test.describe("P4 demo matrix", () => {
  test("all restored demo prospects are visible and carry their critical scenario signals", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));
    await loginAs(page, "admin");

    for (const [name, expectedSnippets] of demoCases) {
      await searchInbox(page, name);
      await expect(page.locator("body")).toContainText(name);
      for (const snippet of expectedSnippets) {
        await expect(page.locator("body")).toContainText(snippet);
      }
    }
  });

  test("special SchoolDrive records avoid forbidden automatic follow-ups", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));
    await loginAs(page, "admin");

    await openInboxConversation(page, "Emma Complet");
    await expect(page.locator("body")).toContainText("complète");
    await expect(page.locator("body")).not.toContainText("Proposer une autre session");
    await expect(page.getByText("Relancer Emma Complet", { exact: false })).toHaveCount(0);

    await openInboxConversation(page, "Rita Roadmap");
    await expect(page.locator("body")).not.toContainText("Revoir le produit Roadmap");
    await expect(page.getByText("Relancer Rita Roadmap", { exact: false })).toHaveCount(0);
  });
});
