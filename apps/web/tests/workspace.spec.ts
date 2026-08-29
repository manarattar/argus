import { expect, test, type Page } from '@playwright/test';

/**
 * End-to-end coverage of the flows a reviewer actually walks through.
 *
 * Tests that need a completed investigation skip with a clear message rather
 * than failing when the database has not been seeded with one - a red suite
 * should mean a broken product, not a missing fixture.
 */

const API = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8000';

async function firstInvestigatedCase(page: Page) {
  const response = await page.request.get(`${API}/api/cases`);
  if (!response.ok()) return null;
  const body = (await response.json()) as {
    cases: { id: string; latest_investigation: { id: string } | null }[];
  };
  return body.cases.find((item) => item.latest_investigation) ?? null;
}

test.describe('Navigation and chrome', () => {
  test('the overview loads and states the operating mode', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Portfolio status' })).toBeVisible();

    // The mode indicator is permanent: a reviewer must never have to guess
    // whether numbers came from a live model or a recording.
    const mode = page.getByText(/Demo mode|Live inference/i).first();
    await expect(mode).toBeVisible();

    // The synthetic-data disclaimer is always on screen.
    await expect(page.getByText(/All data is synthetic/i)).toBeVisible();
  });

  test('every primary destination is reachable', async ({ page }) => {
    const destinations = [
      ['Cases', 'Counterparty reviews'],
      ['Evidence Graph', 'Decision lineage'],
      ['Scenario Lab', 'What would change the assessment'],
      ['Evaluation Lab', 'How well does this actually work'],
      ['AI Operations', 'System operations'],
      ['Audit Trail', 'Audit trail'],
      ['Value Case', 'What this would be worth'],
      ['Architecture', 'How ARGUS is built'],
      ['Settings', 'Runtime configuration'],
    ] as const;

    await page.goto('/');
    for (const [link, heading] of destinations) {
      await page.getByRole('navigation').getByRole('link', { name: link }).click();
      await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible();
    }
  });

  test('the theme toggle switches and persists', async ({ page }) => {
    await page.goto('/');
    const root = page.locator('html');
    const wasDark = await root.evaluate((el) => el.classList.contains('dark'));

    await page.getByRole('button', { name: /Switch to (light|dark) theme/ }).click();
    await expect
      .poll(() => root.evaluate((el) => el.classList.contains('dark')))
      .toBe(!wasDark);

    await page.reload();
    await expect
      .poll(() => root.evaluate((el) => el.classList.contains('dark')))
      .toBe(!wasDark);
  });
});

test.describe('Evaluation Lab', () => {
  test('reports coverage alongside pass rate', async ({ page }) => {
    await page.goto('/evaluation');
    await expect(page.getByRole('heading', { name: /How well does this/ })).toBeVisible();

    const hasRun = await page.getByText('Pass rate', { exact: false }).isVisible();
    if (!hasRun) {
      await page.getByRole('button', { name: /Run evaluation suite/ }).click();
    }

    // Coverage must be shown next to the pass rate so a suite that skipped most
    // of its cases cannot present itself as a strong result.
    await expect(page.getByText('Pass rate')).toBeVisible();
    await expect(page.getByText('Suite coverage')).toBeVisible();
  });

  test('skipped cases are labelled as skipped, never as passes', async ({ page }) => {
    await page.goto('/evaluation');
    const notice = page.getByText(/cases were skipped, not passed/i);
    if (await notice.isVisible()) {
      await expect(notice).toBeVisible();
      await page.getByRole('button', { name: 'skipped' }).click();
      await expect(page.getByText(/Requires a model backend|skipped/i).first()).toBeVisible();
    }
  });
});

test.describe('Value Case', () => {
  test('is labelled illustrative and recomputes when an assumption changes', async ({
    page,
  }) => {
    await page.goto('/value');
    await expect(page.getByText(/Illustrative model/i)).toBeVisible();

    const netValue = page.getByText('Net monthly value').locator('..');
    const before = await netValue.textContent();

    const slider = page.locator('#adoption_rate');
    await slider.fill('0.2');
    await expect.poll(async () => netValue.textContent()).not.toBe(before);
  });
});

test.describe('Architecture', () => {
  test('separates built domains from scoped ones', async ({ page }) => {
    await page.goto('/architecture');
    await expect(page.getByText('Implemented')).toBeVisible();
    await expect(page.getByText('Design-stage extensions')).toBeVisible();
    // Unbuilt domains must say so.
    await expect(page.getByText('design only').first()).toBeVisible();
  });
});

test.describe('Investigation workspace', () => {
  test('shows the assessment, its factors and the review gate', async ({ page }) => {
    const target = await firstInvestigatedCase(page);
    test.skip(!target, 'No completed investigation in the database. Run `make seed-full`.');

    await page.goto(`/cases/${target!.id}`);
    await expect(page.getByText('Provisional assessment')).toBeVisible();

    // The rating must be accompanied by its explanation.
    await expect(page.getByText('How this rating was calculated')).toBeVisible();
    await expect(page.getByText('Composite score')).toBeVisible();

    // The workflow stops for a human.
    await expect(page.getByText('Human review gate')).toBeVisible();
  });

  test('a finding traces to its evidence and quoted source', async ({ page }) => {
    const target = await firstInvestigatedCase(page);
    test.skip(!target, 'No completed investigation in the database. Run `make seed-full`.');

    await page.goto(`/cases/${target!.id}`);
    await page.getByRole('tab', { name: /Findings/ }).click();

    const finding = page.locator('[id^="finding-"]').first();
    await expect(finding).toBeVisible();
    await finding.getByRole('button').first().click();

    await expect(page.getByText(/Supporting evidence/).first()).toBeVisible();
    await expect(page.getByText('Analyst actions')).toBeVisible();
  });

  test('an override demands a rationale before it can be saved', async ({ page }) => {
    const target = await firstInvestigatedCase(page);
    test.skip(!target, 'No completed investigation in the database. Run `make seed-full`.');

    await page.goto(`/cases/${target!.id}`);
    await page.getByRole('tab', { name: /Findings/ }).click();
    await page.locator('[id^="finding-"]').first().getByRole('button').first().click();
    await page.getByRole('button', { name: 'Change severity' }).click();

    const save = page.getByRole('button', { name: /Save and recompute/ });
    await expect(save).toBeDisabled();

    await page.getByPlaceholder(/Why\?/).fill('Recent controls materially reduce residual risk.');
    await page.getByRole('button', { name: 'Minor' }).click();
    await expect(save).toBeEnabled();
  });

  test('the report renders with its audit metadata', async ({ page }) => {
    const target = await firstInvestigatedCase(page);
    test.skip(!target, 'No completed investigation in the database. Run `make seed-full`.');

    await page.goto(`/cases/${target!.id}`);
    await page.getByRole('tab', { name: 'Report' }).click();
    await expect(page.getByRole('heading', { name: /Risk Assessment/ })).toBeVisible();
    await expect(page.getByText('Audit Metadata')).toBeVisible();
  });

  test('the evidence graph highlights lineage on selection', async ({ page }) => {
    const target = await firstInvestigatedCase(page);
    test.skip(!target, 'No completed investigation in the database. Run `make seed-full`.');

    await page.goto(`/graph?investigation=${target!.latest_investigation!.id}`);
    await expect(page.getByText('Decision lineage')).toBeVisible();

    const node = page.locator('svg g[role="button"]').first();
    await node.click();
    await expect(page.getByText('Selected node')).toBeVisible();
  });
});
