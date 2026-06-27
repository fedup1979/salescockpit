const { test, expect } = require("playwright/test");
const { hasCredentials, loginAs, missingCredentialsMessage } = require("../fixtures/auth.cjs");
const { openNav } = require("../helpers/navigation.cjs");

test.describe("P7 guide, pilotage and admin surfaces", () => {
  test("admin surfaces expose required tabs and readiness signals", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));
    await loginAs(page, "admin");

    await openNav(page, "Admin");
    for (const tab of ["État", "Utilisateurs", "Actions admin", "Garde-fous", "Signalements", "Intégrations"]) {
      await expect(page.getByRole("tab", { name: tab })).toBeVisible();
    }
    await expect(page.getByText("SchoolDrive", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Twilio", { exact: false }).first()).toBeVisible();

    await openNav(page, "Pilotage");
    for (const label of ["Flux actifs", "Templates réels", "Templates approuvés", "Cours traités", "États, flux et actions"]) {
      await expect(page.getByText(label, { exact: false }).first()).toBeVisible();
    }

    await openNav(page, "Mode d'emploi");
    for (const label of ["Setter I", "Setter II", "Closer", "Administrateur", "Notes internes"]) {
      await expect(page.getByText(label, { exact: false }).first()).toBeVisible();
    }
  });
});
