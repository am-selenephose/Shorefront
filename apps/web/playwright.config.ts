import { createHash } from 'node:crypto'
import { defineConfig } from '@playwright/test'

const e2eToken = 'portflow-e2e-test-only'
const tokenDigest = createHash('sha256').update(e2eToken).digest('hex')
process.env.PORTFLOW_E2E_OPERATOR_TOKEN = e2eToken

const approvers = JSON.stringify([
  {
    token_sha256: tokenDigest,
    operator_id: 'operator-e2e',
    display_name: 'E2E Operator',
    role: 'operator',
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
        PORTFLOW_DATA_DIR: '/tmp/portflow-e2e-v07',
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
