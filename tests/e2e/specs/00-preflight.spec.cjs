const { test, expect } = require("playwright/test");

test.describe("P0 preflight public", () => {
  test("base URL is explicit and not production unless allowed", async ({ baseURL }) => {
    expect(baseURL).toBeTruthy();
    const url = new URL(baseURL);
    const allowedProduction = process.env.SC_E2E_ALLOW_PRODUCTION === "true";
    const looksProduction = url.port === "8501" || /prod|production/i.test(url.hostname);
    expect(looksProduction && !allowedProduction).toBe(false);
  });

  test("login page loads with stable selectors", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByLabel("E-mail")).toBeVisible();
    await expect(page.getByLabel("Mot de passe")).toBeVisible();
    await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
  });

  test("invalid login is rejected without entering the cockpit", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("E-mail").fill("playwright.invalid@example.com");
    await page.getByLabel("Mot de passe").fill("not-the-password");
    await page.getByRole("button", { name: "Se connecter" }).click();
    await expect(page.getByText("Identifiants invalides")).toBeVisible();
    await expect(page.getByRole("button", { name: /Déconnexion/i })).toHaveCount(0);
  });
});
