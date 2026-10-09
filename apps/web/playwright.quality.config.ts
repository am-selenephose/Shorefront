import {existsSync,mkdtempSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {defineConfig} from '@playwright/test'
const port=Number(process.env.SHORE_QA_PORT||5188)
const api=Number(process.env.SHORE_QA_API_PORT||8188)
const dataDir=mkdtempSync(join(tmpdir(),'shorefront-quality-'))
const buildDir=process.env.SHOREFRONT_E2E_DIST_DIR??'dist'
const chromium=existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined
const selected=process.env.SHORE_QA_BROWSER||'chromium'
if(!['chromium','firefox','webkit'].includes(selected))throw new Error('Invalid QA browser')
export default defineConfig({
 testDir:'./e2e-product',
 testMatch:process.env.SHOREFRONT_QUALITY_ALL?'*.spec.ts':'quality-typography.spec.ts',
 workers:1,fullyParallel:false,timeout:40000,expect:{timeout:8000},
 use:{baseURL:'http://127.0.0.1:'+port,timezoneId:'UTC',trace:'retain-on-failure',screenshot:'only-on-failure',
      browserName:selected as 'chromium'|'firefox'|'webkit',...(selected==='chromium'?{launchOptions:{...(chromium?{executablePath:chromium}:{}),args:['--no-sandbox']}}:{})},
 webServer:[
  {command:'cd ../api && PYTHONPATH=src uv run --no-sync uvicorn shorefront_api.main:app --host 127.0.0.1 --port '+api,
   url:'http://127.0.0.1:'+api+'/readyz',reuseExistingServer:false,
   env:{DATABASE_URL:'sqlite:///'+join(dataDir,'quality.db'),SHOREFRONT_RUNTIME_MODE:'operational',
    SHOREFRONT_INSTALLATION_ID:'quality-browser-regression',SHOREFRONT_ORIGIN:'http://127.0.0.1:'+port,
    SHOREFRONT_BOOTSTRAP_TOKEN:'test-only-bootstrap-for-local-product-browser-suite',
    SHOREFRONT_STATIC_DIR:'',SHOREFRONT_DATA_DIR:dataDir}},
  {command:'./node_modules/.bin/vite preview --config vite.config.ts --outDir '+buildDir+' --host 127.0.0.1 --port '+port+' --strictPort',
   url:'http://127.0.0.1:'+port,reuseExistingServer:false,env:{SHOREFRONT_API_TARGET:'http://127.0.0.1:'+api}}
 ]
})
