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
