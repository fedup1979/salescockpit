const { test, expect } = require("playwright/test");
const { hasCredentials, loginAs, logout, missingCredentialsMessage } = require("../fixtures/auth.cjs");
const { expectAnyVisible, openNav } = require("../helpers/navigation.cjs");

test.describe("P1 auth, sidebar and role access", () => {
  test("admin can log in and navigate main sections", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));

    await loginAs(page, "admin");
    await expectAnyVisible(page, ["Tâches", "Inbox", "Pilotage", "Modèles", "Mode d'emploi", "Admin"]);

    for (const label of ["Tâches", "Inbox", "Mode d'emploi", "Admin"]) {
      await openNav(page, label);
      await expectAnyVisible(page, [label]);
    }

    await expect(page.getByText("Sélecteur de page", { exact: false })).toHaveCount(0);
    await expect(page.getByText("Choisir une page", { exact: false })).toHaveCount(0);
    await logout(page);
  });

  for (const [role, expectedVisible] of [
    ["setter1", ["Tâches", "Inbox", "Mode d'emploi"]],
    ["setter2", ["Tâches", "Inbox", "Mode d'emploi"]],
    ["closer", ["Tâches", "Inbox", "Mode d'emploi"]],
  ]) {
    test(`${role} can log in without admin surface`, async ({ page }) => {
      test.skip(!hasCredentials(role), missingCredentialsMessage(role));

      await loginAs(page, role);
      await expectAnyVisible(page, expectedVisible);
      await expect(page.getByRole("button", { name: /^Admin$/i })).toHaveCount(0);
      await logout(page);
    });
  }
});
