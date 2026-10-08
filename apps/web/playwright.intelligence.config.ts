import {existsSync,mkdtempSync} from 'node:fs'
const systemChromium = process.env.SHOREFRONT_CHROMIUM_EXECUTABLE ?? (existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined)
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {defineConfig} from '@playwright/test'

const dbDir=mkdtempSync(join(tmpdir(),'shorefront-intelligence-e2e-'))
const buildDir=process.env.SHOREFRONT_E2E_DIST_DIR??'dist'

export default defineConfig({
  testDir:'./e2e-intelligence',workers:1,fullyParallel:false,timeout:30000,
  expect:{timeout:8000},
  use:{
    baseURL:'http://127.0.0.1:5177',timezoneId:'UTC',trace:'retain-on-failure',
    screenshot:'only-on-failure',browserName:'chromium',
    launchOptions:{...(systemChromium ? {executablePath:systemChromium} : {}),args:['--no-sandbox']},
  },
  webServer:[
    {
      command:'cd ../api && uv run uvicorn shorefront_api.main:app --host 127.0.0.1 --port 8152',
      url:'http://127.0.0.1:8152/readyz',reuseExistingServer:false,
      env:{
        DATABASE_URL:`sqlite:///${join(dbDir,'intelligence.db')}`,
        SHOREFRONT_RUNTIME_MODE:'operational',SHOREFRONT_SCHEMA_MODE:'migrate',
        SHOREFRONT_INSTALLATION_ID:'intelligence-browser-test',
        SHOREFRONT_ORIGIN:'http://127.0.0.1:5177',
        SHOREFRONT_BOOTSTRAP_TOKEN:'test-only-bootstrap-for-local-product-browser-suite',
        SHOREFRONT_STATIC_DIR:'',SHOREFRONT_DATA_DIR:dbDir,
      },
    },
    {
      command:`./node_modules/.bin/vite preview --config vite.config.ts --outDir ${buildDir} --host 127.0.0.1 --port 5177 --strictPort`,
      url:'http://127.0.0.1:5177',reuseExistingServer:false,
      env:{SHOREFRONT_API_TARGET:'http://127.0.0.1:8152'},
    },
  ],
})
