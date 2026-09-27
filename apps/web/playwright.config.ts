import { createHash } from 'node:crypto'
import { defineConfig } from '@playwright/test'

const e2eToken = 'portflow-e2e-test-only'
const e2eIntegrationToken = 'portflow-e2e-integration-test-only'
const e2eDataDir = '/tmp/portflow-e2e-v016-' + process.pid
const tokenDigest = createHash('sha256').update(e2eToken).digest('hex')
const integrationTokenDigest = createHash('sha256')
  .update(e2eIntegrationToken)
  .digest('hex')
process.env.PORTFLOW_E2E_OPERATOR_TOKEN = e2eToken
process.env.PORTFLOW_E2E_INTEGRATION_TOKEN = e2eIntegrationToken

const approvers = JSON.stringify([
  {
    token_sha256: tokenDigest,
    operator_id: 'operator-e2e',
    display_name: 'E2E Operator',
    role: 'operator',
  },
])

const integrations = JSON.stringify([
  {
    token_sha256: integrationTokenDigest,
    integration_id: 'vessel-runtime-e2e',
    display_name: 'E2E Vessel Runtime',
    vessel_ids: ['v-aurora'],
  },
])

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: {
    timeout: 8_000,
  },
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5175',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    launchOptions: {
      executablePath: '/usr/bin/chromium',
      args: ['--no-sandbox'],
    },
  },
  webServer: [
    {
      command: 'cd ../api && uv run uvicorn portflow_api.main:app --host 127.0.0.1 --port 8150',
      url: 'http://127.0.0.1:8150/healthz',
      timeout: 60_000,
      reuseExistingServer: false,
      env: {
        PORTFLOW_APPROVERS_JSON: approvers,
        PORTFLOW_INTEGRATIONS_JSON: integrations,
        PORTFLOW_DATA_DIR: e2eDataDir,
        PORTFLOW_AIS_URL: 'http://127.0.0.1:9/e2e-unavailable',
        PORTFLOW_AIS_PROVIDER: 'E2E unavailable AIS',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5175 --strictPort',
      url: 'http://127.0.0.1:5175',
      timeout: 60_000,
      reuseExistingServer: false,
      env: {
        PORTFLOW_API_TARGET: 'http://127.0.0.1:8150',
      },
    },
  ],
})
