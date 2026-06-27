const { expect } = require("playwright/test");

const ROLE_ENV = {
  admin: ["SC_E2E_ADMIN_EMAIL", "SC_E2E_ADMIN_PASSWORD"],
  setter1: ["SC_E2E_SETTER1_EMAIL", "SC_E2E_SETTER1_PASSWORD"],
  setter2: ["SC_E2E_SETTER2_EMAIL", "SC_E2E_SETTER2_PASSWORD"],
  closer: ["SC_E2E_CLOSER_EMAIL", "SC_E2E_CLOSER_PASSWORD"],
};

function credentialsFor(role) {
  const keys = ROLE_ENV[role];
  if (!keys) {
    throw new Error(`Unknown role: ${role}`);
  }
  const [emailKey, passwordKey] = keys;
  const sharedPassword = process.env.SC_E2E_SHARED_PASSWORD || "";
  return {
    email: process.env[emailKey] || "",
    password: process.env[passwordKey] || sharedPassword,
    emailKey,
    passwordKey,
  };
}

function hasCredentials(role) {
  const { email, password } = credentialsFor(role);
  return Boolean(email && password);
}

function missingCredentialsMessage(role) {
  const { emailKey, passwordKey } = credentialsFor(role);
  return `Credentials missing: set ${emailKey} and ${passwordKey}, or set SC_E2E_SHARED_PASSWORD for the shared password`;
}

async function loginAs(page, role) {
  const { email, password } = credentialsFor(role);
  if (!email || !password) {
    throw new Error(missingCredentialsMessage(role));
  }

  await page.goto("/");
  await expect(page.getByLabel("E-mail")).toBeVisible();
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();

  await expect(page.getByText("Identifiants invalides")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Déconnexion/i })).toBeVisible();
}

async function logout(page) {
  const logoutButton = page.getByRole("button", { name: /Déconnexion/i });
  if (await logoutButton.count()) {
    await logoutButton.first().click();
    await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
  }
}

module.exports = {
  credentialsFor,
  hasCredentials,
  loginAs,
  logout,
  missingCredentialsMessage,
};
