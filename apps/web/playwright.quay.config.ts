import {mkdtempSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {defineConfig} from '@playwright/test'

const directory=mkdtempSync(join(tmpdir(),'shorefront-quay-regression-'))
const built=process.env.SHOREFRONT_QUAY_BUILD??'/tmp/shorefront-quay-green-build'
const port=Number(process.env.SHOREFRONT_QUAY_PORT||5186)
const api=Number(process.env.SHOREFRONT_QUAY_API_PORT||8167)
export default defineConfig({
 testDir:'./e2e-product',testMatch:process.env.SHOREFRONT_QUAY_ALL?'*.spec.ts':'quay-fullscreen.spec.ts',
 workers:1,fullyParallel:false,timeout:30000,expect:{timeout:8000},
 use:{baseURL:'http://127.0.0.1:'+port,timezoneId:'UTC',trace:'retain-on-failure',
 screenshot:'only-on-failure',browserName:'chromium',
 launchOptions:{executablePath:'/usr/bin/chromium',args:['--no-sandbox']}},
 webServer:[
  {command:'cd ../api && PYTHONPATH=src uv run --no-sync uvicorn shorefront_api.main:app --host 127.0.0.1 --port '+api,
   url:'http://127.0.0.1:'+api+'/readyz',reuseExistingServer:false,
   env:{DATABASE_URL:'sqlite:///'+join(directory,'quay.db'),SHOREFRONT_RUNTIME_MODE:'operational',
    SHOREFRONT_INSTALLATION_ID:'quay-browser-regression',SHOREFRONT_ORIGIN:'http://127.0.0.1:'+port,
    SHOREFRONT_BOOTSTRAP_TOKEN:'test-only-bootstrap-for-local-product-browser-suite',
    SHOREFRONT_STATIC_DIR:'',SHOREFRONT_DATA_DIR:directory}},
  {command:'./node_modules/.bin/vite preview --config vite.config.ts --outDir '+built+' --host 127.0.0.1 --port '+port+' --strictPort',
   url:'http://127.0.0.1:'+port,reuseExistingServer:false,env:{SHOREFRONT_API_TARGET:'http://127.0.0.1:'+api}},
 ]
})
