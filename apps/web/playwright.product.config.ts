import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { defineConfig } from '@playwright/test'

const dataDir = mkdtempSync(join(tmpdir(), 'shorefront-product-e2e-'))
const requestedBrowser=process.env.SHOREFRONT_E2E_BROWSER ?? 'chromium'
if(!['chromium','firefox','webkit'].includes(requestedBrowser)) throw new Error('SHOREFRONT_E2E_BROWSER must be chromium, firefox or webkit')
const browserName=requestedBrowser as 'chromium'|'firefox'|'webkit'

export default defineConfig({
  testDir: './e2e-product', workers: 1, fullyParallel: false, timeout: 30000,
  expect: { timeout: 8000 },
  use: { baseURL: 'http://127.0.0.1:5176', timezoneId:'UTC', trace: 'retain-on-failure', screenshot: 'only-on-failure',
    browserName,
    ...(browserName==='chromium' ? {launchOptions:{executablePath:'/usr/bin/chromium',args:['--no-sandbox']}} : {}) },
  webServer: [
    { command: 'cd ../api && uv run uvicorn shorefront_api.main:app --host 127.0.0.1 --port 8151',
      url: 'http://127.0.0.1:8151/readyz', reuseExistingServer: false,
      env: { DATABASE_URL: `sqlite:///${join(dataDir, 'product.db')}`, SHOREFRONT_RUNTIME_MODE: 'operational',
        SHOREFRONT_INSTALLATION_ID: 'product-browser-test', SHOREFRONT_ORIGIN: 'http://127.0.0.1:5176',
        SHOREFRONT_BOOTSTRAP_TOKEN: 'test-only-bootstrap-for-local-product-browser-suite',
        SHOREFRONT_STATIC_DIR: '', SHOREFRONT_DATA_DIR: dataDir } },
    { command: './node_modules/.bin/vite preview --config vite.config.ts --host 127.0.0.1 --port 5176 --strictPort',
      url: 'http://127.0.0.1:5176', reuseExistingServer: false,
      env: { SHOREFRONT_API_TARGET: 'http://127.0.0.1:8151' } },
  ],
})
