import { expect, test } from '@playwright/test'

const operatorToken = process.env.PORTFLOW_E2E_OPERATOR_TOKEN || 'portflow-e2e-test-only'

test('incident to authenticated recovery receipt survives reload', async ({ page, request }) => {
  const reset = await request.post('/api/v1/demo/reset')
  expect(reset.ok()).toBeTruthy()

  await page.goto('/')

  const incidentButton = page.getByRole('button', { name: /B07 Berth Crunch/i })
  await expect(incidentButton).toBeVisible()
  await incidentButton.click()

  await expect(page.getByText('Move pc-nova to Berth 15')).toBeVisible()

  const unauthenticatedApply = page.getByRole('button', { name: 'Authenticate to apply' }).first()
  await expect(unauthenticatedApply).toBeDisabled()

  const tokenInput = page.getByLabel('Operator access token')
  await tokenInput.fill(operatorToken)
  await page.getByRole('button', { name: 'Verify' }).click()

  await expect(page.getByText('E2E Operator').first()).toBeVisible()
  await expect(page.getByText(/operator-e2e · operator/)).toBeVisible()

  const apply = page.getByRole('button', { name: 'Approve & apply' }).first()
  await expect(apply).toBeEnabled()
  await apply.click()

  await expect(page.getByText(/RECENT OPERATOR RECEIPTS · 1/)).toBeVisible()
  await expect(page.getByText(/E2E Operator · operator/).last()).toBeVisible()

  const conflicts = await request.get('/api/v1/berth-conflicts')
  expect(conflicts.ok()).toBeTruthy()
  expect(await conflicts.json()).toEqual([])

  const storedToken = await page.evaluate(() =>
    sessionStorage.getItem('portflow.operator_token'),
  )
  expect(storedToken).toBe(operatorToken)

  await page.reload()
  await expect(page.getByText('E2E Operator').first()).toBeVisible()
  await expect(page.getByText(/RECENT OPERATOR RECEIPTS · 1/)).toBeVisible()
})


test('operator ingests healthy recorded AIS while stale adapter stays blocked', async ({ page, request }) => {
  const reset = await request.post('/api/v1/demo/reset')
  expect(reset.ok()).toBeTruthy()

  await page.goto('/')

  const initialSource = page.locator('[data-source-id="synthetic-ais"]')
  await expect(initialSource).toBeVisible()
  await expect(initialSource.locator('.source-mode.synthetic')).toHaveText('synthetic')

  const staleAdapter = page.locator('[data-adapter-id="stale-weather-fixture"]')
  await expect(staleAdapter).toBeVisible()
  await expect(staleAdapter.getByRole('button', { name: 'Stale blocked' })).toBeDisabled()

  const aisAdapter = page.locator('[data-adapter-id="recorded-ais"]')
  await expect(aisAdapter.getByRole('button', { name: 'Authenticate' })).toBeDisabled()

  await page.getByLabel('Operator access token').fill(operatorToken)
  await page.getByRole('button', { name: 'Verify' }).click()
  await expect(page.getByText('E2E Operator').first()).toBeVisible()

  const ingest = aisAdapter.getByRole('button', { name: 'Ingest fixture' })
  await expect(ingest).toBeEnabled()
  await ingest.click()

  const recordedSource = page.locator('[data-source-id="recorded-ais"]')
  await expect(recordedSource).toBeVisible()
  await expect(recordedSource.locator('.source-mode.recorded')).toHaveText('recorded')
  await expect(recordedSource.getByText('PortFlow recorded AIS fixture')).toBeVisible()

  const harbor = await request.get('/api/v1/harbor')
  expect(harbor.ok()).toBeTruthy()
  const state = await harbor.json()
  const aurora = state.vessels.find((vessel: { id: string }) => vessel.id === 'v-aurora')
  expect(aurora.source_id).toBe('recorded-ais')

  const aisSource = state.data_sources.find(
    (source: { source_id: string }) => source.source_id === 'recorded-ais',
  )
  expect(aisSource.source_id).toBe('recorded-ais')
  expect(aisSource.mode).toBe('recorded')
  expect(aisSource.health).toBe('healthy')
  expect(state.data_disclaimer.toLowerCase()).toContain('recorded fixture')

  await page.reload()
  await expect(page.getByText('E2E Operator').first()).toBeVisible()
  await expect(page.locator('[data-source-id="recorded-ais"]')).toBeVisible()
  await expect(
    page.locator('[data-adapter-id="stale-weather-fixture"]').getByRole('button', { name: 'Stale blocked' }),
  ).toBeDisabled()
})


test('bunker loss renders the branched DAG and operator recovery clears shared blockage', async ({ page, request }) => {
  const reset = await request.post('/api/v1/demo/reset')
  expect(reset.ok()).toBeTruthy()

  await page.goto('/')

  const scenarioButton = page.getByRole('button', { name: /^Bunker Barge 4 Unavailable\b/i })
  await expect(scenarioButton).toBeVisible()
  await scenarioButton.click()

  await expect(page.locator('#incidents').getByText('Assigned bunker barge unavailable')).toBeVisible()

  const auroraDag = page.locator('[data-service-dag="pc-aurora"]')
  const gloryDag = page.locator('[data-service-dag="pc-glory"]')
  await expect(auroraDag).toBeVisible()
  await expect(gloryDag).toBeVisible()
  const bunker12 = page.locator('.resource-row').filter({ hasText: 'Bunker Barge 12' })
  await expect(bunker12).toContainText('planned maintenance')
  await expect(bunker12).toContainText('BLOCKED')

  await expect(
    auroraDag.locator('[data-service-kind="customs"] em'),
  ).toHaveText('FROM CARGO + DOCS')
  await expect(
    auroraDag.locator('[data-service-kind="departure"] em'),
  ).toHaveText('FROM CARGO + BUNKER + STORES + CUSTOMS + GATE')

  await expect(auroraDag.locator('[data-service-kind="bunker"]')).toContainText('60m')
  await expect(auroraDag.locator('[data-service-kind="bunker"]')).toHaveClass(/blocked/)
  await expect(auroraDag.locator('[data-service-kind="departure"]')).toHaveClass(/blocked/)
  await expect(gloryDag.locator('[data-service-kind="bunker"]')).toHaveClass(/blocked/)
  await expect(gloryDag.locator('[data-service-kind="departure"]')).toHaveClass(/blocked/)

  const preferredRecovery = page
    .locator('article.recovery-card')
    .filter({ hasText: 'Bunker Barge 12' })
    .first()
  await expect(preferredRecovery).toBeVisible()
  await expect(preferredRecovery).toContainText('DATA CONFIDENCE · DEMO')
  await expect(preferredRecovery).toContainText('synthetic demo sources')
  await expect(
    preferredRecovery.getByRole('button', { name: 'Authenticate to apply' }),
  ).toBeDisabled()

  await page.getByLabel('Operator access token').fill(operatorToken)
  await page.getByRole('button', { name: 'Verify' }).click()
  await expect(page.getByText('E2E Operator').first()).toBeVisible()

  const approve = preferredRecovery.getByRole('button', { name: 'Approve & apply' })
  await expect(approve).toBeEnabled()
  await approve.click()

  await expect(page.getByText(/RECENT OPERATOR RECEIPTS · 1/)).toBeVisible()
  await expect(auroraDag.locator('[data-service-kind="bunker"]')).not.toHaveClass(/blocked/)
  await expect(auroraDag.locator('[data-service-kind="departure"]')).not.toHaveClass(/blocked/)
  await expect(gloryDag.locator('[data-service-kind="bunker"]')).not.toHaveClass(/blocked/)
  await expect(gloryDag.locator('[data-service-kind="departure"]')).not.toHaveClass(/blocked/)

  for (const callId of ['pc-aurora', 'pc-glory']) {
    const graphResponse = await request.get('/api/v1/port-calls/' + callId + '/dependency-graph')
    expect(graphResponse.ok()).toBeTruthy()
    const graph = await graphResponse.json()
    const nodes = Object.fromEntries(
      graph.nodes.map((node: { kind: string; state: string }) => [node.kind, node]),
    )
    expect(nodes.bunker.state).not.toBe('blocked')
    expect(nodes.departure.state).not.toBe('blocked')
  }
})


test('compound dual-resource recovery links both incidents and clears tug/bunker blockage', async ({ page, request }) => {
  const reset = await request.post('/api/v1/demo/reset')
  expect(reset.ok()).toBeTruthy()

  await page.goto('/')

  const scenarioButton = page.getByRole('button', {
    name: 'Tug 14 + Bunker Barge 4 Unavailable',
  })
  await expect(scenarioButton).toBeVisible()
  await scenarioButton.click()

  const compoundRecovery = page
    .locator('article.recovery-card')
    .filter({ hasText: 'COMPOUND · 2 INCIDENTS' })
    .first()

  await expect(compoundRecovery).toBeVisible()
  await expect(compoundRecovery).toContainText('Compound recovery: Tug 22 + Bunker Barge 9')
  await expect(compoundRecovery).toContainText('tug:')
  await expect(compoundRecovery).toContainText('bunker:')
  await expect(
    compoundRecovery.getByRole('button', { name: 'Authenticate to apply' }),
  ).toBeDisabled()

  await page.getByLabel('Operator access token').fill(operatorToken)
  await page.getByRole('button', { name: 'Verify' }).click()
  await expect(page.getByText('E2E Operator').first()).toBeVisible()

  const approve = compoundRecovery.getByRole('button', { name: 'Approve & apply' })
  await expect(approve).toBeEnabled()
  await approve.click()

  await expect(page.getByText(/RECENT OPERATOR RECEIPTS · 1/)).toBeVisible()

  for (const callId of ['pc-aurora', 'pc-glory']) {
    const graphResponse = await request.get('/api/v1/port-calls/' + callId + '/dependency-graph')
    expect(graphResponse.ok()).toBeTruthy()
    const graph = await graphResponse.json()
    const nodes = Object.fromEntries(
      graph.nodes.map((node: { kind: string; state: string }) => [node.kind, node]),
    )
    expect(nodes.tug.state).not.toBe('blocked')
    expect(nodes.bunker.state).not.toBe('blocked')
    expect(nodes.departure.state).not.toBe('blocked')
  }
})
