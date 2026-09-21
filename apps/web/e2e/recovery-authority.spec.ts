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
})
