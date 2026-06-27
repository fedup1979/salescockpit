const { test, expect } = require("playwright/test");
const { hasCredentials, loginAs, missingCredentialsMessage } = require("../fixtures/auth.cjs");
const { openNav } = require("../helpers/navigation.cjs");

test.describe("P3 mutation guard", () => {
  test("bug report flow is disabled unless mutation flag is explicit", async ({ page }) => {
    test.skip(!hasCredentials("admin"), missingCredentialsMessage("admin"));
    test.skip(process.env.SC_E2E_ALLOW_MUTATION === "true", "Mutation guard only runs when mutating E2E tests are disabled");

    await loginAs(page, "admin");
    await openNav(page, "Bug");
    await expect(page.getByText("Test fonction bug Playwright", { exact: false })).toHaveCount(0);
  });
});
