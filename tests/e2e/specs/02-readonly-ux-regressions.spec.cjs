const { test, expect } = require("playwright/test");
const { hasCredentials, loginAs, missingCredentialsMessage } = require("../fixtures/auth.cjs");
const { expectAnyVisible, expectNoHtmlFragments, openNav } = require("../helpers/navigation.cjs");

test.describe("P2 read-only UX regressions", () => {
  test("guide uses V1 terminology", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));

    await loginAs(page, "admin");
    await openNav(page, "Mode d'emploi");
    await expectAnyVisible(page, ["Setter I", "Setter II", "Closer", "Administrateur"]);
    await expect(page.getByText("Notes internes", { exact: false }).first()).toBeVisible();
  });

  test("tasks surface does not show raw HTML fragments", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));

    await loginAs(page, "admin");
    await openNav(page, "Tâches");
    await expectNoHtmlFragments(page);
  });

  test("demo special cases are searchable or visible in operational surfaces", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));

    await loginAs(page, "admin");
    await openNav(page, "Inbox");
    await expectAnyVisible(page, ["À traiter", "En suspens", "Terminées", "Toutes"]);
  });
});
