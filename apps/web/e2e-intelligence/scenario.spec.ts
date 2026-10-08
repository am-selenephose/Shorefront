import {expect,test} from '@playwright/test'

test('operational plan compares recorded berth scenarios without modifying the call', async ({page},testInfo)=>{
  const cap=await (await page.request.get('/api/v1/runtime/capabilities')).json()
  await page.goto(cap.needs_setup?'/#setup=test-only-bootstrap-for-local-product-browser-suite':'/')
  if(cap.needs_setup) await page.getByLabel('Full name').fill('Port Owner')
  await page.getByLabel('Email',{exact:true}).fill('owner@example.test')
  await page.getByLabel('Password',{exact:true}).fill('test-only customer passphrase 42')
  await page.getByRole('button',{name:cap.needs_setup?'Create workspace':'Sign in',exact:true}).click()
  await expect(page.getByRole('link',{name:'Plan',exact:true})).toBeVisible()
  const auth=await page.request.get('/api/v1/auth/me')
  expect(auth.status(),await auth.text()).toBe(200)
  const me=await auth.json()
  const headers={Origin:new URL(page.url()).origin,'X-CSRF-Token':me.csrf_token}
  const workspace=await (await page.request.get('/api/v1/workspace')).json()
  const existing=new Set(workspace.records.map((r:{kind:string;record_id:string})=>r.kind+':'+r.record_id))
  for(const [kind,id,payload] of [
    ['port','scenario-port',{name:'Scenario Harbor',timezone:'UTC'}],
    ['berth','scenario-berth-a',{name:'West Quay',port_id:'scenario-port',max_length_m:300}],
    ['berth','scenario-berth-b',{name:'East Quay',port_id:'scenario-port',max_length_m:300}],
    ['vessel','scenario-ship-a',{name:'MV Horizon',length_m:200}],
    ['vessel','scenario-ship-b',{name:'MV Anchor',length_m:210}],
    ['call','scenario-call-a',{vessel_id:'scenario-ship-a',berth_id:'scenario-berth-a',eta:'2026-11-20T10:00:00Z',etd:'2026-11-20T15:00:00Z'}],
    ['call','scenario-call-b',{vessel_id:'scenario-ship-b',berth_id:'scenario-berth-b',eta:'2026-11-20T11:00:00Z',etd:'2026-11-20T17:00:00Z'}],
  ] as const){
    if(existing.has(kind+':'+id))continue
    const response=await page.request.post('/api/v1/records/'+kind,{headers:{...headers,'Idempotency-Key':id},data:{record_id:id,expected_revision:0,source:'Customer planning desk',payload}})
    expect(response.status(),await response.text()).toBe(201)
  }
  await page.goto('/#plan')
  await expect(page.getByRole('heading',{name:'Compare a berth plan before it becomes an order.'})).toBeVisible()
  const lab=page.getByRole('region',{name:'What-if berth scenario planning'})
  await lab.getByLabel('Call to simulate').selectOption('scenario-call-a')
  await lab.getByLabel('Proposed berth').selectOption('scenario-berth-b')
  await lab.getByRole('button',{name:'Compare this scenario'}).click()
  await expect(lab).toContainText('Recorded berth overlap')
  await expect(lab).toContainText('UNCOMMITTED SCENARIO')
  const original=(await (await page.request.get('/api/v1/workspace')).json()).records.find((r:{record_id:string})=>r.record_id==='scenario-call-a')
  expect(original.payload.berth_id).toBe('scenario-berth-a')
  await page.screenshot({path:testInfo.outputPath('real-what-if-planner.png'),fullPage:true})
  await page.setViewportSize({width:390,height:844})
  await expect(page.getByRole('region',{name:'What-if berth scenario planning'})).toBeVisible()
  const horizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)
  expect(horizontalOverflow,'Mobile page must not overflow horizontally').toBeLessThanOrEqual(2)
  await page.screenshot({path:testInfo.outputPath('scenario-mobile.png'),fullPage:true})
})
