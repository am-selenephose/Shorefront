import {expect,test} from '@playwright/test'

test('what-if alternative becomes the exact packet a supervisor approves', async ({page,browser})=>{
  test.setTimeout(65000)
  const initial=await (await page.request.get('/api/v1/runtime/capabilities')).json()
  await page.goto(initial.needs_setup?'/#setup=test-only-bootstrap-for-local-product-browser-suite':'/')
  if(initial.needs_setup) await page.getByLabel('Full name').fill('Port Owner')
  await page.getByLabel('Email',{exact:true}).fill('owner@example.test')
  await page.getByLabel('Password',{exact:true}).fill('test-only customer passphrase 42')
  await page.getByRole('button',{name:initial.needs_setup?'Create workspace':'Sign in',exact:true}).click()
  await expect(page.getByRole('link',{name:'Plan',exact:true})).toBeVisible()
  const auth=await (await page.request.get('/api/v1/auth/me')).json()
  const headers={Origin:new URL(page.url()).origin,'X-CSRF-Token':auth.csrf_token}
  const rows=[
    ['port','handoff-port',{name:'Decision Harbor',timezone:'UTC'}],
    ['berth','handoff-west',{name:'West Decision Quay',port_id:'handoff-port',max_length_m:300}],
    ['berth','handoff-east',{name:'East Decision Quay',port_id:'handoff-port',max_length_m:300}],
    ['vessel','handoff-vessel',{name:'MV Decision Bridge',length_m:180}],
    ['call','handoff-call',{vessel_id:'handoff-vessel',berth_id:'handoff-west',eta:'2026-11-25T10:00:00Z',etd:'2026-11-25T15:00:00Z'}],
  ] as const
  for(const [kind,id,payload] of rows){
    const r=await page.request.post('/api/v1/records/'+kind,{headers:{...headers,'Idempotency-Key':'di-'+id},data:{record_id:id,expected_revision:0,source:'Operator verified schedule',payload}})
    expect(r.status(),await r.text()).toBe(201)
  }
  await page.goto('/#plan')
  const lab=page.getByRole('region',{name:'What-if berth scenario planning'})
  await lab.getByLabel('Call to simulate').selectOption('handoff-call')
  await lab.getByLabel('Proposed berth').selectOption('handoff-east')
  await lab.getByRole('button',{name:'Compare this scenario'}).click()
  await expect(lab.getByRole('region',{name:'Source-aware scenario impact'})).toBeVisible()
  await lab.getByRole('button',{name:'Save exact scenario for supervisor review'}).click()
  await expect(lab).toContainText('Decision packet recorded:')
  const preserved=await (await page.request.get('/api/v1/workspace')).json()
  expect(preserved.records.find((r:{record_id:string})=>r.record_id==='handoff-call').payload.berth_id).toBe('handoff-west')
  await lab.getByRole('button',{name:'Open exact packet in Recovery'}).click()
  await expect(page).toHaveURL(/#recovery/)
  await expect(page.getByRole('heading',{name:'Review source-aware berth scenario for MV Decision Bridge'})).toBeVisible()
  await expect(page.getByRole('region',{name:'Operational impact review for Operator-proposed scenario (exact recorded inputs)'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Approve recorded plan'})).toBeDisabled()
  const packetResponse=await page.request.get('/api/v1/decisions')
  expect(packetResponse.status()).toBe(200)
  const packet=(await packetResponse.json()).find((p:{question:string})=>p.question==='Review source-aware berth scenario for MV Decision Bridge')
  expect(packet).toBeTruthy()
  const selected=packet.options.find((o:{label:string})=>o.label.startsWith('Operator-proposed scenario'))
  expect(selected.eligible).toBe(true)
  expect(selected.call_payload.berth_id).toBe('handoff-east')

  const invitation=await page.request.post('/api/v1/auth/invitations',{headers:{...headers,'Idempotency-Key':'di-supervisor-invite'},
    data:{email:'decision-supervisor@example.test',role:'supervisor'}})
  expect(invitation.status(),await invitation.text()).toBe(201)
  const token=(await invitation.json()).invitation_token
  const supervisorContext=await browser.newContext()
  try{
    const supervisor=await supervisorContext.newPage()
    await supervisor.goto('http://127.0.0.1:5177')
    await supervisor.getByRole('button',{name:'I have an invitation'}).click()
    await supervisor.getByLabel('Invitation token').fill(token)
    await supervisor.getByLabel('Full name').fill('Decision Supervisor')
    await supervisor.getByLabel('Email',{exact:true}).fill('decision-supervisor@example.test')
    await supervisor.getByLabel('Password',{exact:true}).fill('test-only customer passphrase 42')
    await supervisor.getByRole('button',{name:'Accept invitation'}).click()
    await supervisor.goto('/#recovery')
    await expect(supervisor.getByRole('heading',{name:'Review source-aware berth scenario for MV Decision Bridge'})).toBeVisible()
    await supervisor.getByRole('button',{name:'Review packet'}).click()
    await supervisor.getByLabel('Option to approve').selectOption(selected.id)
    await supervisor.getByLabel('Approval reason').fill('Reviewed recorded berth and source impact')
    await supervisor.getByRole('button',{name:'Approve recorded plan'}).click()
    await expect(supervisor.getByRole('heading',{name:'Approval recorded'})).toBeVisible()
    const current=await (await supervisor.request.get('/api/v1/workspace')).json()
    expect(current.records.find((r:{record_id:string})=>r.record_id==='handoff-call').payload.berth_id).toBe('handoff-east')
    expect((await (await supervisor.request.get('/api/v1/evidence')).json()).audit_valid).toBe(true)
  }finally{await supervisorContext.close()}
})
