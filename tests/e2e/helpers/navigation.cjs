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

async function searchInbox(page, query) {
  await openNav(page, "Inbox");
  const search = page.getByRole("textbox", { name: "Recherche", exact: true });
  await expect(search).toBeVisible();
  await search.fill("");
  await search.fill(query);
  await search.press("Enter");
  await page.waitForTimeout(1200);
  const allTab = page.getByRole("tab", { name: /Toutes/i });
  if (await allTab.count()) {
    await allTab.first().click();
    await page.waitForTimeout(500);
  }
}

async function openInboxConversation(page, query, visibleName = query) {
  await searchInbox(page, query);
  await expect(page.getByText(visibleName, { exact: false }).first()).toBeVisible();
  const firstView = page.getByRole("button", { name: "Voir" }).first();
  if (await firstView.count()) {
    await firstView.click();
    await page.waitForTimeout(800);
  }
  await expect(page.getByText(visibleName, { exact: false }).first()).toBeVisible();
}

async function clickFirstVisible(locator) {
  const count = await locator.count();
  for (let index = 0; index < count; index += 1) {
    const candidate = locator.nth(index);
    if (await candidate.isVisible().catch(() => false)) {
      await candidate.click();
      return;
    }
  }
  throw new Error("No visible element found for locator");
}

module.exports = {
  clickFirstVisible,
  expectAnyVisible,
  expectNoHtmlFragments,
  openInboxConversation,
  openNav,
  searchInbox,
};
