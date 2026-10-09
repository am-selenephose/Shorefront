import {expect,test} from '@playwright/test'

test('source-backed resource assignment and measured-outcome coverage appear in operator workflows',async({page})=>{
  test.setTimeout(75000)
  const capabilities=await (await page.request.get('/api/v1/runtime/capabilities')).json()
  await page.goto(capabilities.needs_setup?'/#setup=test-only-bootstrap-for-local-product-browser-suite':'/')
  if(capabilities.needs_setup) await page.getByLabel('Full name').fill('Port Owner')
  await page.getByLabel('Email',{exact:true}).fill('owner@example.test')
  await page.getByLabel('Password',{exact:true}).fill('test-only customer passphrase 42')
  await page.getByRole('button',{name:capabilities.needs_setup?'Create workspace':'Sign in',exact:true}).click()
  await expect(page.getByRole('link',{name:'Plan',exact:true})).toBeVisible()
  const session=await (await page.request.get('/api/v1/auth/me')).json()
  const headers={Origin:new URL(page.url()).origin,'X-CSRF-Token':session.csrf_token}
  const records=[
    ['port','resource-check-port',{name:'Resource Check Harbor',timezone:'UTC'}],
    ['berth','resource-check-berth',{name:'Pilot Quay',port_id:'resource-check-port'}],
    ['vessel','resource-check-vessel',{name:'MV Pilot Test'}],
    ['call','resource-check-call',{vessel_id:'resource-check-vessel',berth_id:'resource-check-berth',eta:'2026-11-25T09:00:00Z',etd:'2026-11-25T15:00:00Z'}],
    ['resource','resource-check-pilot',{name:'Pilot A',port_id:'resource-check-port',resource_type:'pilot',available:true}],
    ['resource_assignment','resource-check-assignment',{call_id:'resource-check-call',resource_id:'resource-check-pilot',
      starts_at:'2026-11-25T08:45:00Z',ends_at:'2026-11-25T10:00:00Z',
      status:'confirmed',confirmation_note:'Dispatch confirmation from named pilot desk'}]
  ] as const
  for(const [kind,id,payload] of records){
    const response=await page.request.post('/api/v1/records/'+kind,{headers:{...headers,'Idempotency-Key':'resource-check-'+id},
      data:{record_id:id,expected_revision:0,source:'Named port operator',payload}})
    expect(response.status(),await response.text()).toBe(201)
  }
  await page.goto('/#plan')
  await page.reload() // machine-origin changes need a fresh workspace snapshot
  const board=page.getByRole('region',{name:'Specific call resource assignments'})
  await expect(board).toBeVisible()
  await expect(board).toContainText('MV Pilot Test')
  await expect(board).toContainText('Pilot A')
  await expect(board).toContainText('confirmed')
  await expect(board.getByRole('button',{name:'Assign resource to call'})).toBeVisible()
  await page.goto('/#recovery')
  const metrics=page.getByRole('region',{name:'Measured decision outcome coverage'})
  await expect(metrics).toBeVisible()
  await expect(metrics).toContainText('APPROVED DECISIONS')
  await expect(metrics).toContainText('OBSERVATION COVERAGE')
  // The earlier supervisor-handoff test may have created a genuine approved
  // packet in this shared disposable fixture. Do not assume zero approvals.
  await expect(metrics).toContainText('Missing observations are excluded')
  await page.setViewportSize({width:390,height:844})
  await expect(metrics).toBeVisible()
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)
  expect(overflow,'mobile page must not grow past viewport').toBeLessThanOrEqual(2)
})
