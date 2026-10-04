import {expect, test} from '@playwright/test'
import {workflowSession} from './workflow-fixture'

for (const validAt of ['2099-01-01T00:00:00Z', '2025-01-01T00:00:00Z']) {
  test(`editor resolves a hidden revision at ${validAt} through explicit review`, async ({page}, testInfo) => {
    const session = await workflowSession(page)
    const id = `temporal-${crypto.randomUUID()}`
    const headers = {Origin:'http://127.0.0.1:5176','X-CSRF-Token':session.csrf_token}
    async function save(revision:number, name:string, effective:string) {
      const result = await page.request.post('/api/v1/records/port', {
        headers:{...headers,'Idempotency-Key':crypto.randomUUID()},
        data:{record_id:id,expected_revision:revision,valid_at:effective,source:'Temporal regression fixture',payload:{name,timezone:'UTC'}},
      })
      expect(result.status()).toBe(201)
      return result.json()
    }
    await save(0, id, '2026-01-01T00:00:00Z')
    const head = await save(1, `Head ${id}`, validAt)
    await page.goto('/#records')
    await page.getByRole('button',{name:`Edit ${id}`,exact:true}).click()
    const editor = page.getByRole('region',{name:'Record editor'})
    await editor.getByLabel('Name',{exact:true}).fill(`Draft ${id}`)
    await editor.getByRole('button',{name:'Save record',exact:true}).click()
    await expect(editor.getByRole('alert')).toContainText('Record changed')
    await expect(editor.getByLabel('Name',{exact:true})).toHaveValue(`Draft ${id}`)
    await editor.getByRole('button',{name:'Review latest version',exact:true}).click()
    await expect(editor.getByRole('region',{name:'Latest recorded version'})).toContainText(`Head ${id}`)
    await expect(editor.getByRole('region',{name:'Latest recorded version'})).toContainText(head.valid_at)
    await expect(editor.getByLabel('Name',{exact:true})).toHaveValue(`Draft ${id}`)
    const reviewed = await page.request.get(`/api/v1/records/port/${id}/head`)
    expect((await reviewed.json()).revision).toBe(2)
    for (const width of [375, 768, 1280]) {
      await page.setViewportSize({width,height:900})
      expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.screenshot({path:testInfo.outputPath(`review-${width}.png`),fullPage:true})
    }
    await page.getByRole('button',{name:'Switch to dark mode',exact:true}).click()
    await page.screenshot({path:testInfo.outputPath('review-dark.png'),fullPage:true})
    await page.context().setOffline(true)
    await expect(editor.getByRole('button',{name:'Replace draft with latest version',exact:true})).toBeDisabled()
    await expect(editor.getByLabel('Name',{exact:true})).toHaveValue(`Draft ${id}`)
    await page.context().setOffline(false)
    await page.getByRole('button',{name:'Retry connection',exact:true}).click()
    await editor.getByRole('button',{name:'Replace draft with latest version',exact:true}).click()
    await expect(editor.getByLabel('Name',{exact:true})).toHaveValue(`Head ${id}`)
    await expect(editor).toContainText('Saving creates a new version effective now')
    await editor.getByLabel('Name',{exact:true}).fill(`Corrected ${id}`)
    await editor.getByRole('button',{name:'Save record',exact:true}).click()
    await expect(editor).toHaveCount(0)
    const workspace = await (await page.request.get('/api/v1/workspace')).json()
    expect(workspace.records.find((r:{record_id:string})=>r.record_id===id)).toMatchObject({revision:3,payload:{name:`Corrected ${id}`}})
    const evidence = await (await page.request.get('/api/v1/evidence')).json()
    const versions = evidence.versions.filter((r:{record_id:string})=>r.record_id===id)
    expect(versions).toHaveLength(3)
    expect(versions[1]).toMatchObject({revision:2,valid_at:head.valid_at,payload:{name:`Head ${id}`}})
    expect(evidence.audit_valid).toBe(true)
  })
}

test('reviewed future-only relationships are preserved until the operator explicitly clears them', async ({page}) => {
  const session = await workflowSession(page)
  const id = `future-link-${crypto.randomUUID()}`
  const headers = {Origin:'http://127.0.0.1:5176','X-CSRF-Token':session.csrf_token}
  async function save(kind:string, recordId:string, revision:number, payload:Record<string,unknown>, validAt:string) {
    const result = await page.request.post(`/api/v1/records/${kind}`, {
      headers:{...headers,'Idempotency-Key':crypto.randomUUID()},
      data:{record_id:recordId,expected_revision:revision,valid_at:validAt,source:'Temporal relationship fixture',payload},
    })
    expect(result.status(), await result.text()).toBe(201)
  }
  await save('incident',`${id}-incident`,0,{title:'Future incident',severity:'medium',status:'open'},'2099-01-01T00:00:00Z')
  const payload = {title:id,due_at:'2099-01-02T00:00:00Z',status:'open'}
  await save('task',id,0,payload,'2026-01-01T00:00:00Z')
  await save('task',id,1,{...payload,incident_id:`${id}-incident`},'2099-01-01T00:00:00Z')
  await page.goto('/#records')
  await page.getByLabel('Record category').selectOption('task')
  await page.getByRole('button',{name:`Edit ${id}`,exact:true}).click()
  const editor = page.getByRole('region',{name:'Record editor'})
  await editor.getByRole('button',{name:'Save record',exact:true}).click()
  await expect(editor.getByRole('alert')).toContainText('Record changed')
  await editor.getByRole('button',{name:'Review latest version',exact:true}).click()
  await editor.getByRole('button',{name:'Replace draft with latest version',exact:true}).click()
  await expect(editor.getByRole('combobox',{name:/^Incident/})).toHaveValue(`${id}-incident`)
  await editor.getByRole('button',{name:'Save record',exact:true}).click()
  await expect(editor.getByRole('alert')).toContainText('existing effective incident')
  await expect(editor.getByRole('combobox',{name:/^Incident/})).toHaveValue(`${id}-incident`)
  const unchanged = await page.request.get(`/api/v1/records/task/${id}/head`)
  expect((await unchanged.json()).revision).toBe(2)
  await editor.getByRole('combobox',{name:/^Incident/}).selectOption('')
  await editor.getByRole('button',{name:'Save record',exact:true}).click()
  await expect(editor).toHaveCount(0)
  const corrected = await page.request.get(`/api/v1/records/task/${id}/head`)
  expect(await corrected.json()).toMatchObject({revision:3,payload:{incident_id:null}})
})
