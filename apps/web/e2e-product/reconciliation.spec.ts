import {expect,test} from '@playwright/test'
import {workflowSession,writeFact} from './workflow-fixture'

test('integration disagreement is reviewed and resolved without erasing either source version', async ({page}) => {
  const session=await workflowSession(page)
  await writeFact(page,'vessel','reconcile-browser-vessel',{name:'MV Browser Resolve',imo:'7654321',length_m:200})

  const source=await page.request.post('/api/v1/connections/sources',{
    headers:{Origin:'http://127.0.0.1:5176','X-CSRF-Token':session.csrf_token},
    data:{id:'reconcile-browser-source',name:'Reconciliation browser source',allowed_kinds:['vessel']},
  })
  expect(source.status(),await source.text()).toBe(201)
  const token=(await source.json()).token as string
  const ingest=await page.request.post('/api/v1/integrations/reconcile-browser-source/records',{
    headers:{Authorization:'Bearer '+token,'Idempotency-Key':'reconcile-browser-ingest'},
    data:{records:[{kind:'vessel',record_id:'reconcile-browser-vessel',expected_revision:1,payload:{name:'MV Browser Resolve',imo:'7654321',length_m:214}}]},
  })
  expect(ingest.status(),await ingest.text()).toBe(201)

  await page.getByRole('link',{name:'Evidence',exact:true}).click()
  const desk=page.getByRole('region',{name:'Source reconciliation'})
  await expect(desk).toBeVisible()
  await expect(desk).toContainText('1 OPEN')
  const conflict=desk.locator('[data-conflict-id]').first()
  await expect(conflict).toContainText('MV Browser Resolve')
  await expect(conflict.getByRole('region',{name:'Baseline version 1'})).toContainText('200')
  await expect(conflict.getByRole('region',{name:'Challenger version 2'})).toContainText('214')
  await expect(conflict).toContainText('integration:reconcile-browser-source')

  await conflict.getByLabel('Resolution note').fill('Port registry checked by browser test operator; retain registered length.')
  const resolution=page.waitForResponse(response=>response.request().method()==='POST'&&response.url().includes('/api/v1/reconciliation/conflicts/')&&response.url().endsWith('/resolve'))
  await conflict.getByRole('button',{name:'Accept V1'}).click()
  expect((await resolution).status()).toBe(200)
  await expect(desk).toContainText('0 OPEN')
  await desk.getByText(/Resolved disagreements/).click()
  await expect(desk).toContainText('Accepted V1')
  await expect(desk).toContainText('materialized as V3')

  const head=await page.request.get('/api/v1/records/vessel/reconcile-browser-vessel/head')
  expect(head.status()).toBe(200)
  expect(await head.json()).toMatchObject({revision:3,source:expect.stringMatching(/^reconciliation:/),payload:{length_m:200}})
  const evidence=await page.request.get('/api/v1/evidence')
  expect(evidence.status()).toBe(200)
  const exported=await evidence.json()
  expect(exported.audit_valid).toBe(true)
  expect(exported.conflicts).toHaveLength(1)
  expect(exported.conflicts[0]).toMatchObject({state:'resolved',accepted_revision:1,resolution_revision:3})
})
