const { expect } = require("playwright/test");

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function openNav(page, label) {
  const exactButton = page.getByRole("button", { name: new RegExp(`^${escapeRegex(label)}$`, "i") });
  if (await exactButton.count()) {
    await exactButton.first().click();
    await page.waitForTimeout(300);
    return;
  }

  const text = page.getByText(label, { exact: true });
  await expect(text.first()).toBeVisible();
  await text.first().click();
  await page.waitForTimeout(300);
}

async function expectAnyVisible(page, labels) {
  for (const label of labels) {
    const locator = page.getByText(label, { exact: false });
    if ((await locator.count()) > 0 && await locator.first().isVisible().catch(() => false)) {
      return label;
    }
  }
  throw new Error(`None of these labels are visible: ${labels.join(", ")}`);
}

async function expectNoHtmlFragments(page) {
  await expect(page.getByText("</div>", { exact: false })).toHaveCount(0);
  await expect(page.getByText("</span>", { exact: false })).toHaveCount(0);
}

module.exports = {
  expectAnyVisible,
  expectNoHtmlFragments,
  openNav,
};
