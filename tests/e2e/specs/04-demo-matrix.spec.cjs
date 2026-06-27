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
  ["Émilie Morel", ["rappel closing d'Émilie Morel"]],
  ["Mathieu Garnier", ["Relancer Mathieu Garnier", "Va signer"]],
  ["Océane Petit", ["avant début de cours"]],
  ["Hugo Muller", ["Revoir le statut de contact de Hugo Muller", "Ne plus contacter"]],
  ["Irina Lopes", ["A signé"]],
  ["Chloé Schmid", ["Chloé Schmid"]],
  ["Philippe Aubert", ["Non pertinent"]],
  ["Inconnu(e)", ["Répondre à Inconnu(e)"]],
  ["Laura Admin Démo", ["Valider le wording du modèle financement"]],
  ["François Admin Démo", ["Relire la logique de transitions"]],
  ["Tiago Admin Démo", ["Vérifier le mapping SchoolDrive"]],
  ["Camille Laurent", ["Relancer Camille Laurent"]],
  ["Luc Moreau", ["Appeler et documenter l'appel setting de Luc Moreau"]],
  ["Sonia Mercier", ["Reprise manuelle setter de Sonia Mercier"]],
  ["Yves Caron", ["Reprise manuelle closer de Yves Caron"]],
  ["Emma Complet", ["Proposer une autre session à Emma Complet", "complète"]],
  ["Rita Roadmap", ["Revoir le produit Roadmap de Rita Roadmap", "Roadmap"]],
];

test.describe("P4 demo matrix", () => {
  test("all restored demo prospects are visible and carry their critical scenario signals", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));
    await loginAs(page, "admin");

    for (const [name, expectedSnippets] of demoCases) {
      await searchInbox(page, name);
      await expect(page.getByText(name, { exact: false }).first()).toBeVisible();
      for (const snippet of expectedSnippets) {
        await expect(page.getByText(snippet, { exact: false }).first()).toBeVisible();
      }
    }
  });

  test("special SchoolDrive records route to human review instead of normal flow", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));
    await loginAs(page, "admin");

    await openInboxConversation(page, "Emma Complet");
    await expect(page.getByText("Proposer une autre session à Emma Complet", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("complète", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Relancer Emma Complet", { exact: false })).toHaveCount(0);

    await openInboxConversation(page, "Rita Roadmap");
    await expect(page.getByText("Revoir le produit Roadmap de Rita Roadmap", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Relancer Rita Roadmap", { exact: false })).toHaveCount(0);
  });
});
