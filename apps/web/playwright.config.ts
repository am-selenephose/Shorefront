import { createHash } from 'node:crypto'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { defineConfig } from '@playwright/test'

const e2eToken = 'shorefront-e2e-test-only'
const e2eIntegrationToken = 'shorefront-e2e-integration-test-only'
const e2eDataDir = mkdtempSync(join(tmpdir(), 'shorefront-e2e-'))
const tokenDigest = createHash('sha256').update(e2eToken).digest('hex')
const integrationTokenDigest = createHash('sha256')
  .update(e2eIntegrationToken)
  .digest('hex')
process.env.SHOREFRONT_E2E_OPERATOR_TOKEN = e2eToken
process.env.SHOREFRONT_E2E_INTEGRATION_TOKEN = e2eIntegrationToken

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
      command: 'cd ../api && uv run uvicorn shorefront_api.main:app --host 127.0.0.1 --port 8150',
      url: 'http://127.0.0.1:8150/healthz',
      timeout: 60_000,
      reuseExistingServer: false,
      env: {
        DATABASE_URL: `sqlite:///${join(e2eDataDir, 'test.db')}`,
        SHOREFRONT_SCHEMA_MODE: 'migrate',
        SHOREFRONT_RUNTIME_MODE: 'training',
        SHOREFRONT_PUBLIC_MODE: '0',
        SHOREFRONT_DEMO_CONTROLS: '1',
        SHOREFRONT_STATIC_DIR: '',
        SHOREFRONT_APPROVERS_JSON: approvers,
        SHOREFRONT_INTEGRATIONS_JSON: integrations,
        SHOREFRONT_DATA_DIR: e2eDataDir,
        SHOREFRONT_AIS_URL: 'http://127.0.0.1:9/e2e-unavailable',
        SHOREFRONT_AIS_PROVIDER: 'E2E unavailable AIS',
        SHOREFRONT_WEATHER_URL: '',
        SHOREFRONT_BERTH_PLAN_URL: '',
      },
    },
    {
      command: process.env.SHOREFRONT_E2E_BUILT === '1'
        ? './node_modules/.bin/vite preview --config vite.config.ts --host 127.0.0.1 --port 5175 --strictPort'
        : 'npm run dev -- --host 127.0.0.1 --port 5175 --strictPort',
      url: 'http://127.0.0.1:5175',
      timeout: 60_000,
      reuseExistingServer: false,
      env: {
        SHOREFRONT_API_TARGET: 'http://127.0.0.1:8150',
      },
    },
  ],
})
