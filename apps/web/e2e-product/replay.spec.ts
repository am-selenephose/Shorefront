import {expect, test, type Page, type Route} from '@playwright/test'

const origin = 'http://127.0.0.1:5176'
const password = 'rotated browser-only passphrase 789'

async function historicalFixture(page: Page) {
  const capabilities = await (await page.request.get('/api/v1/runtime/capabilities')).json()
  const auth = await page.request.post(`/api/v1/auth/${capabilities.needs_setup ? 'bootstrap' : 'login'}`, {
    headers: {Origin: origin},
    data: {email: 'owner@example.test', password, ...(capabilities.needs_setup ? {
      display_name: 'Port Owner', bootstrap_token: 'test-only-bootstrap-for-local-product-browser-suite',
    } : {})},
  })
  expect(auth.ok()).toBeTruthy()
  const session = await auth.json()
  const id = `replay-${crypto.randomUUID()}`
  const headers = {Origin: origin, 'X-CSRF-Token': session.csrf_token}
  async function save(revision: number, name: string, source: string) {
    const response = await page.request.post('/api/v1/records/port', {
      headers: {...headers, 'Idempotency-Key': crypto.randomUUID()},
      data: {record_id: id, expected_revision: revision, valid_at: '2026-01-01T06:00:00Z',
        source, payload: {name, timezone: revision ? 'Asia/Karachi' : 'UTC'}},
    })
    expect(response.ok()).toBeTruthy()
    return response.json()
  }
  const original = await save(0, `Original harbor ${id}`, 'Harbor agent email 06:00Z')
  // Chromium's datetime-local fill accepts second precision reliably. Keep a real
  // one-second knowledge-time gap so the selected clock remains between revisions.
  await page.waitForTimeout(1200)
  const corrected = await save(1, `Corrected harbor ${id}`, 'Signed operator correction 06:20Z')
  const originalMs = new Date(original.known_at).getTime()
  const correctedMs = new Date(corrected.known_at).getTime()
  const betweenMs = Math.ceil(originalMs / 1000) * 1000
  expect(betweenMs).toBeLessThan(correctedMs)
  const earlier = new Date(betweenMs).toISOString().slice(0, 19)
  const later = new Date(Math.ceil(correctedMs / 1000) * 1000 + 1000).toISOString().slice(0, 19)
  await page.goto('/#evidence')
  await expect(page.getByRole('heading', {name: 'Every correction keeps its past.'})).toBeVisible()
  return {original, corrected, earlier, later, user: session.user}
}

async function selectClocks(page: Page, known: string) {
  await page.getByLabel('Known by', {exact: true}).fill(known)
  await page.getByLabel('Effective at', {exact: true}).fill('2026-01-02T06:00')
  await page.getByRole('button', {name: 'Reconstruct view', exact: true}).click()
}

test('reconstruction preserves original payload, source and actor alongside current differences', async ({page}) => {
  const {original, corrected, earlier, user} = await historicalFixture(page)
  await selectClocks(page, earlier)
  const replay = page.locator('section').filter({has: page.getByRole('heading', {name: /^Historical facts/})}).first()
  // Dropping historical payload/provenance must fail even when the revision name remains visible.
  await expect(replay).toContainText('Harbor agent email 06:00Z')
  await expect(replay).toContainText(user.name)
  await expect(replay).toContainText(user.id)
  await expect(replay).toContainText(original.known_at)
  await expect(replay).toContainText(original.valid_at)
  await expect(replay).toContainText('Read-only historical view')
  const changes = replay.getByRole('table', {name: `Changes for ${original.payload.name}`})
  await expect(changes).toContainText(original.payload.name)
  await expect(changes).toContainText(corrected.payload.name)
  await expect(changes).toContainText('UTC')
  await expect(changes).toContainText('Asia/Karachi')
  await expect(replay.getByRole('button', {name: /Save|Edit|Approve/})).toHaveCount(0)
  const version = page.locator('.product-history > li').filter({hasText: original.payload.name})
  await version.getByText('Inspect version', {exact: true}).click()
  await expect(version).toContainText(user.id)
  await expect(version).toContainText('UTC')
  await expect(page.getByRole('button', {name: 'Export evidence', exact: true})).toBeVisible()
})

test('a delayed historical request cannot replace the most recently selected clocks', async ({page}) => {
  const {original, corrected, earlier, later} = await historicalFixture(page)
  let release!: () => void
  const held = new Promise<void>(resolve => {release = resolve})
  let intercepted!: () => void
  const firstReceived = new Promise<void>(resolve => {intercepted = resolve})
  let delivered!: () => void
  const firstDelivered = new Promise<void>(resolve => {delivered = resolve})
  let first = true
  const handler = async (route: Route) => {
    if (!first) {await route.continue(); return}
    first = false
    const response = await route.fetch()
    intercepted()
    await held
    await route.fulfill({response})
    delivered()
  }
  await page.route('**/api/v1/workspace?**', handler)
  try {
    await selectClocks(page, earlier)
    await firstReceived
    await selectClocks(page, later)
    const replay = page.getByRole('region', {name: 'Historical reconstruction'})
    await expect(replay.getByRole('heading', {name: corrected.payload.name, exact: true})).toBeVisible()
    release()
    await firstDelivered
    await expect(replay.getByRole('heading', {name: corrected.payload.name, exact: true})).toBeVisible()
    await expect(replay.getByRole('heading', {name: original.payload.name, exact: true})).toHaveCount(0)
    await expect(replay).toContainText(new Date(`${later}Z`).toISOString())
  } finally {
    release()
    await page.unroute('**/api/v1/workspace?**', handler)
  }
})
