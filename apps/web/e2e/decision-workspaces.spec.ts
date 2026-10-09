import { expect, test, type WebSocketRoute } from '@playwright/test'

test('focused workspaces have deep links, history and presentation-only role lenses', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'What needs attention now?' })).toBeVisible()
  await expect(page.locator('#ledger')).not.toBeVisible()
  const nav = page.getByRole('navigation', { name: 'Shorefront workspace' })
  await nav.getByRole('link', { name: 'Plan', exact: true }).click()
  await expect(page).toHaveURL(/#plan$/)
  await expect(page.getByRole('heading', { name: 'Plan the next move' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Plan the next move' })).toBeVisible()
  await nav.getByRole('link', { name: 'Recovery', exact: true }).click()
  await page.getByLabel('Role lens').selectOption('Harbor Master')
  await expect(page.getByText('Not authenticated', { exact: true })).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Plan the next move' })).toBeVisible()
})

test('guided demo shows engine results and simulated receipt without operational writes', async ({ page }, info) => {
  await page.goto('/')
  const writes: string[] = []
  page.on('request', request => {
    if (request.url().includes('/api/') && request.method() !== 'GET') writes.push(request.url())
  })
  await page.getByRole('button', { name: 'Guided demo', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'A disruption. A decision. A record.' })).toBeVisible()
  await page.getByRole('button', { name: 'Introduce tug disruption' }).click()
  await expect(page.getByRole('heading', { name: 'Tug 14 is unavailable' })).toBeVisible()
  await page.getByRole('button', { name: 'Compare recovery options' }).click()
  // The engine supplies two feasible options for this fixture; do not fabricate a third.
  await expect(page.locator('.comparison-column')).toHaveCount(3)
  await expect(page.getByText('Model assumptions', { exact: true })).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('guided-comparison.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('button', { name: 'Simulate approval of Option A' }).click()
  await expect(page.getByText('Simulated receipt · not an operational approval')).toBeVisible()
  expect(writes).toEqual([])
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('guided-receipt.png'), fullPage: true })
  await page.getByRole('button', { name: 'Operations', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'What needs attention now?' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /Attention queue/ })).toBeInViewport()
})

test('initial transport failure has a working retry instead of an endless loading screen', async ({ page }) => {
  await page.route('**/api/v1/harbor', route => route.abort())
  await page.routeWebSocket('**/ws/harbor', () => {})
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Retry connection' })).toBeVisible()
  await page.unroute('**/api/v1/harbor')
  await page.getByRole('button', { name: 'Retry connection' }).click()
  await expect(page.getByRole('heading', { name: 'What needs attention now?' })).toBeVisible()
})

test('mobile Pulse and architecture are readable in both themes', async ({ page }, info) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'What needs attention now?' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /Attention queue/ })).toBeInViewport()
  for (const mode of ['light', 'dark']) {
    if (mode === 'dark') await page.getByRole('button', { name: 'Dark mode', exact: true }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375)
    await expect(page.getByRole('button', { name: 'Operations', exact: true })).toHaveCSS('color', mode === 'dark' ? 'rgb(25, 47, 50)' : 'rgb(236, 234, 193)')
    await page.screenshot({ path: info.outputPath(`pulse-mobile-${mode}.png`), fullPage: true, animations: 'disabled' })
  }
  await page.getByRole('button', { name: 'Architecture', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Inside Shorefront' })).toBeVisible()
  await expect(page.getByText('Not yet implemented', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375)
})

test('demo actions use the coastal action palette and keyboard focus', async ({ page }) => {
  await page.goto('/')
  const action = page.getByRole('button', { name: 'Explore a disruption ↗' })
  await expect(action).toHaveCSS('background-color', 'rgb(254, 175, 119)')
  await expect(action).toHaveCSS('color', 'rgb(25, 47, 50)')
  await action.focus()
  await expect(action).toHaveCSS('outline-style', 'solid')
})

test('failed recovery queries are not presented as an empty successful result', async ({ page }) => {
  await page.route('**/api/v1/recovery/proposals', route => route.fulfill({ status: 503, body: '{}' }))
  await page.goto('/#recovery')
  await expect(page.getByRole('alert').filter({ hasText: 'Recovery proposals unavailable' })).toBeVisible()
  await expect(page.getByText('No mitigation proposal required.')).not.toBeVisible()
  await page.unroute('**/api/v1/recovery/proposals')
  await page.getByRole('button', { name: 'Recalculate', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Recovery proposals unavailable' })).not.toBeVisible()
})

test('silent open transport expires and disables operational mutation controls', async ({ page }) => {
  await page.routeWebSocket('**/ws/harbor', () => {})
  await page.goto('/#control-tower')
  await expect(page.locator('.shell')).toBeVisible()
  await expect(page.locator('.system-state')).toHaveText('STALE DATA · READ ONLY', { timeout: 16000 })
  await expect(page.getByRole('button', { name: /B07 Berth Crunch/ })).toBeDisabled()
})

test('protected runtime hides shared demo controls while retaining isolated guided demo', async ({ page }) => {
  await page.route('**/api/v1/runtime/capabilities', route => route.fulfill({ json: { runtime_mode: 'training', demo_controls_enabled: false } }))
  await page.goto('/#exceptions')
  await expect(page.getByText('Shared demo controls disabled')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reset demo', exact: true })).not.toBeVisible()
  await page.getByRole('button', { name: 'Guided demo', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Introduce tug disruption' })).toBeVisible()
})

test('canonical decision revision refreshes comparison and proposals without call changes', async ({ page }) => {
  const comparison = await (await page.request.get('/api/v1/recovery/comparison')).json()
  const before = comparison.current
  const after = structuredClone(before)
  after.decision_revision = 'source-revision-after'
  after.data_sources[0].provider = 'Updated source attribution'
  let current = before
  let stream: WebSocketRoute | undefined
  let proposalQueries = 0
  await page.route('**/api/v1/harbor', route => route.fulfill({ json: before }))
  await page.route('**/api/v1/recovery/comparison', route => route.fulfill({ json: { ...comparison, current } }))
  await page.route('**/api/v1/recovery/proposals', async route => {
    proposalQueries++
    await route.continue()
  })
  await page.routeWebSocket('**/ws/harbor', socket => { stream = socket })
  await page.goto('/#recovery')
  const column = page.locator('.comparison-column').first()
  await expect(column).toBeVisible()
  await expect.poll(() => proposalQueries).toBeGreaterThan(0)
  const queriesBeforeChange = proposalQueries
  current = after
  stream!.send(JSON.stringify(after))
  await expect(column).toContainText('Updated source attribution')
  await expect.poll(() => proposalQueries).toBeGreaterThan(queriesBeforeChange)
})

test('ending an operator session stays available when the stream disconnects', async ({ page }) => {
  let stream: WebSocketRoute | undefined
  await page.routeWebSocket('**/ws/harbor', socket => { stream = socket })
  await page.goto('/#recovery')
  await page.getByLabel('Operator access token').fill('shorefront-e2e-test-only')
  await page.getByRole('button', { name: 'Verify', exact: true }).click()
  await expect(page.getByRole('button', { name: 'End session' })).toBeEnabled()
  // Hold the reconnect timer: a short reconnection must not mask disabled logout.
  await page.clock.install()
  await page.clock.pauseAt(new Date())
  stream!.close()
  await expect(page.locator('.system-state')).toContainText('DISCONNECTED')
  const logout = page.getByRole('button', { name: 'End session' })
  await expect(logout).toBeEnabled()
  await logout.click()
  await expect(page.getByText('Not authenticated', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('shorefront.operator_token'))).toBeNull()
})

test('malformed nested stream data retains the last usable operations picture', async ({ page }) => {
  let stream: WebSocketRoute | undefined
  await page.routeWebSocket('**/ws/harbor', socket => { stream = socket })
  await page.goto('/')
  const heading = page.getByRole('heading', { name: 'What needs attention now?' })
  await expect(heading).toBeVisible()
  const invalid = await (await page.request.get('/api/v1/harbor')).json()
  invalid.port_calls = [null]
  stream!.send(JSON.stringify(invalid))
  await expect(page.getByRole('status').filter({ hasText: 'Invalid stream data' })).toBeVisible()
  await expect(heading).toBeVisible()
  await expect(page.locator('.side-foot')).toContainText('CONNECTED')
  await page.getByRole('link', { name: 'Exceptions', exact: true }).click()
  await expect(page.getByRole('button', { name: /B07 Berth Crunch/ })).toBeDisabled()
})

for (const view of ['comparison', 'demo'] as const) {
  test(`malformed successful ${view} response shows retry instead of crashing`, async ({ page }) => {
    const endpoint = view === 'comparison' ? '**/api/v1/recovery/comparison' : '**/api/v1/demo/story'
    await page.route(endpoint, route => route.fulfill({ json: { options: [null] } }))
    await page.goto('/#recovery')
    if (view === 'demo') await page.getByRole('button', { name: 'Guided demo', exact: true }).click()
    const retry = page.getByRole('button', { name: view === 'demo' ? 'Retry demo' : 'Retry comparison', exact: true })
    await expect(retry).toBeVisible()
    await page.unroute(endpoint)
    await retry.click()
    await expect(page.getByRole('heading', { name: view === 'demo' ? 'A disruption. A decision. A record.' : 'Compare before committing' })).toBeVisible()
  })
}
