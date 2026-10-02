import { expect, test } from '@playwright/test'

const operatorToken = process.env.SHOREFRONT_E2E_OPERATOR_TOKEN || 'shorefront-e2e-test-only'
const integrationToken = process.env.SHOREFRONT_E2E_INTEGRATION_TOKEN || 'shorefront-e2e-integration-test-only'

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
    sessionStorage.getItem('shorefront.operator_token'),
  )
  expect(storedToken).toBe(operatorToken)

  await page.reload()
  await expect(page.getByText('E2E Operator').first()).toBeVisible()
  await expect(page.getByText(/RECENT OPERATOR RECEIPTS · 1/)).toBeVisible()
  await page.getByRole('button', { name: 'End session' }).click()
  await expect(page.getByText('Not authenticated', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('shorefront.operator_token'))).toBeNull()
  await page.reload()
  await expect(page.getByText('Not authenticated', { exact: true })).toBeVisible()
})


test('operator ingests healthy recorded AIS while stale adapter stays blocked', async ({ page, request }) => {
  const reset = await request.post('/api/v1/demo/reset')
  expect(reset.ok()).toBeTruthy()

  await page.goto('/')

  const initialSource = page.locator('[data-source-id="synthetic-ais"]')
  const calibrationSource = page.locator('[data-source-id="synthetic-service-calibration"]')
  await expect(calibrationSource).toBeVisible()
  await expect(calibrationSource).toContainText('SERVICE CALIBRATION')

  await expect(initialSource).toBeVisible()
  await expect(initialSource.locator('.source-mode.synthetic')).toHaveText('synthetic')

  const staleAdapter = page.locator('[data-adapter-id="stale-weather-fixture"]')
  await expect(staleAdapter).toBeVisible()
  await expect(staleAdapter.getByRole('button', { name: 'Stale blocked' })).toBeDisabled()

  const liveBackoffAdapter = page.locator('[data-adapter-id="live-ais"]')
  await expect(liveBackoffAdapter).toBeVisible()
  await expect(liveBackoffAdapter).toContainText('RETRY BACKOFF')
  await expect(
    liveBackoffAdapter.getByRole('button', { name: 'Retry scheduled' }),
  ).toBeDisabled()

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
  await expect(recordedSource.getByText('Shorefront recorded AIS fixture')).toBeVisible()

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
  const applyResponsePromise = page.waitForResponse(response =>
    response.request().method() === 'POST' &&
    response.url().includes('/api/v1/recovery/proposals/') &&
    response.url().endsWith('/apply'),
  )
  await approve.click()
  const applyResponse = await applyResponsePromise
  expect(applyResponse.ok()).toBeTruthy()

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
  const compoundApplyPromise = page.waitForResponse(response =>
    response.request().method() === 'POST' &&
    response.url().includes('/api/v1/recovery/proposals/') &&
    response.url().endsWith('/apply'),
  )
  await approve.click()
  const compoundApplyResponse = await compoundApplyPromise
  expect(compoundApplyResponse.ok()).toBeTruthy()

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

test('stale selected recovery resource loads ranked contingency and requires re-approval', async ({ page, request }) => {
  const reset = await request.post('/api/v1/demo/reset')
  expect(reset.ok()).toBeTruthy()

  await page.goto('/')

  const scenarioButton = page.getByRole('button', {
    name: /^Bunker Barge 4 Unavailable\b/i,
  })
  await expect(scenarioButton).toBeVisible()
  await scenarioButton.click()

  const staleRecovery = page
    .locator('article.recovery-card')
    .filter({ hasText: 'Bunker Barge 12' })
    .first()
  await expect(staleRecovery).toBeVisible()

  await page.getByLabel('Operator access token').fill(operatorToken)
  await page.getByRole('button', { name: 'Verify' }).click()
  await expect(page.getByText('E2E Operator').first()).toBeVisible()

  const failedBackup = await request.post('/api/v1/incidents', {
    data: {
      incident_type: 'bunker_unavailable',
      target_port_call_id: 'pc-aurora',
      target_resource_id: 'bunker-barge-12',
      impact_minutes: 0,
    },
  })
  expect(failedBackup.ok()).toBeTruthy()
  expect((await failedBackup.json()).target_resource_id).toBe('bunker-barge-12')

  const staleApprove = staleRecovery.getByRole('button', { name: 'Approve & apply' })
  await expect(staleApprove).toBeEnabled()
  const staleApplyPromise = page.waitForResponse(response =>
    response.request().method() === 'POST' &&
    response.url().includes('/api/v1/recovery/proposals/') &&
    response.url().endsWith('/apply'),
  )
  await staleApprove.click()
  const staleApplyResponse = await staleApplyPromise
  expect(staleApplyResponse.status()).toBe(409)

  const contingencyNotice = page.getByText(
    /CONTINGENCY · Previous recovery plan is stale\./,
  )
  await expect(contingencyNotice).toBeVisible()
  await expect(contingencyNotice).toContainText('bunker-barge-12')
  await expect(contingencyNotice).toContainText('new explicit approval is required')

  const replacement = page
    .locator('article.recovery-card')
    .filter({ hasText: 'Bunker Barge 9' })
    .first()
  await expect(replacement).toBeVisible()
  await expect(
    page.locator('article.recovery-card').filter({ hasText: 'Bunker Barge 12' }),
  ).toHaveCount(0)

  const graphBefore = await request.get(
    '/api/v1/port-calls/pc-aurora/dependency-graph',
  )
  expect(graphBefore.ok()).toBeTruthy()
  const beforeNodes = Object.fromEntries(
    (await graphBefore.json()).nodes.map(
      (node: { kind: string; state: string }) => [node.kind, node],
    ),
  )
  expect(beforeNodes.bunker.state).toBe('blocked')

  const replacementApprove = replacement.getByRole('button', {
    name: 'Approve & apply',
  })
  await expect(replacementApprove).toBeEnabled()
  const replacementApplyPromise = page.waitForResponse(response =>
    response.request().method() === 'POST' &&
    response.url().includes('/api/v1/recovery/proposals/') &&
    response.url().endsWith('/apply'),
  )
  await replacementApprove.click()
  const replacementApplyResponse = await replacementApplyPromise
  expect(replacementApplyResponse.ok()).toBeTruthy()

  await expect(page.getByText(/RECENT OPERATOR RECEIPTS · 1/)).toBeVisible()
  await expect(contingencyNotice).toHaveCount(0)

  const graphAfter = await request.get(
    '/api/v1/port-calls/pc-aurora/dependency-graph',
  )
  expect(graphAfter.ok()).toBeTruthy()
  const afterNodes = Object.fromEntries(
    (await graphAfter.json()).nodes.map(
      (node: { kind: string; state: string }) => [node.kind, node],
    ),
  )
  expect(afterNodes.bunker.state).not.toBe('blocked')
  expect(afterNodes.departure.state).not.toBe('blocked')
})


test('shore operator sees privacy-minimized vessel exception resolution lifecycle', async ({ page, request }) => {
  const reset = await request.post('/api/v1/demo/reset')
  expect(reset.ok()).toBeTruthy()

  const exceptionRef = 'mrt-exception-0123456789abcdefabcd'
  const privateActor = 'private-second-engineer'
  const privateReason = 'private supervisor rationale must stay onboard'
  const lifecycle = [
    ['crew.exception.opened', 'open', 'medium'],
    ['crew.attention.acknowledged', 'acknowledged', 'low'],
    ['crew.attention.claimed', 'claimed', 'low'],
    ['crew.attention.resolved', 'resolved', 'low'],
  ] as const
  const base = Date.now()

  for (const [index, [runtimeEventType, state, risk]] of lifecycle.entries()) {
    const response = await request.post('/api/v1/integration/vessel-events', {
      headers: {
        Authorization: 'Bearer ' + integrationToken,
      },
      data: {
        contract_version: 'portflow.vessel-event.v1',
        event_id: 'evt-e2e-exception-' + index,
        occurred_at: new Date(base + index * 1000).toISOString(),
        vessel_id: 'v-aurora',
        port_call_id: 'pc-aurora',
        event_type: 'constraint',
        sequence: 1200 + index,
        source_system: 'maritime-runtime:v-aurora',
        payload: {
          runtime_event_type: runtimeEventType,
          title: 'producer private title',
          summary: 'producer private summary',
          risk,
          source_sequence: 1200 + index,
          exception_ref: exceptionRef,
          category: 'crew_operational_exception',
          state,
          privacy_minimized: true,
          advisory_only: true,
          execution_authorized: false,
          actor_id: privateActor,
          resolution_reason: privateReason,
        },
        evidence_refs: [],
      },
    })
    expect(response.ok()).toBeTruthy()
  }

  await page.goto('/')
  const panel = page.locator('#vessel-exceptions')
  await expect(panel.getByText('OPERATOR SESSION REQUIRED')).toBeVisible()

  await page.getByLabel('Operator access token').fill(operatorToken)
  await page.getByRole('button', { name: 'Verify' }).click()

  await expect(panel.locator('.vessel-exception-status.resolved')).toHaveText('RESOLVED')
  await expect(panel.getByText('Crew operational exception resolved')).toBeVisible()
  await expect(panel.getByText('4 LIFECYCLE EVENTS')).toBeVisible()
  await expect(panel.getByText(/SEQ 1200.*1203/)).toBeVisible()

  const lifecycleTrail = panel.locator(
    `[data-exception-history="${exceptionRef}"]`,
  )
  await expect(lifecycleTrail).toBeVisible()
  await expect(
    lifecycleTrail.locator('[data-exception-state]'),
  ).toHaveText(['OPEN', 'ACKNOWLEDGED', 'CLAIMED', 'RESOLVED'])
  await expect(panel).toContainText('PRIVACY MINIMIZED')
  await expect(panel).toContainText('NO ACTUATION')
  await expect(panel).not.toContainText(privateActor)
  await expect(panel).not.toContainText(privateReason)
  await expect(panel).not.toContainText('producer private title')
  await expect(panel).not.toContainText('producer private summary')
})

test("Shorefront public product shell keeps advisory authority visible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Shorefront", { exact: true })).toBeVisible();
  await expect(page.getByText("MARITIME · SHORE", { exact: true })).toBeVisible();
  await expect(page.getByText("SHOREFRONT · OPERATIONS CONTROL TOWER", { exact: true })).toBeVisible();
  await expect(page.getByText("NO VESSEL ACTUATION", { exact: true })).toBeVisible();
  await expect(page).toHaveTitle(/Shorefront/);
});

test('retired browser credential is cleared and does not authenticate', async ({ page }) => {
  await page.addInitScript(token => {
    sessionStorage.setItem('portflow.operator_token', token)
  }, operatorToken)
  await page.goto('/')
  await expect(page.locator('.shell')).toBeVisible()
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('portflow.operator_token'))).toBeNull()
  await expect(page.getByRole('button', { name: 'Verify' })).toBeVisible()
})
