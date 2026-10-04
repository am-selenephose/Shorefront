import {expect, type Page} from '@playwright/test'

export const workflowPassword = 'rotated browser-only passphrase 789'
export async function workflowSession(page: Page) {
  const runtime = await (await page.request.get('/api/v1/runtime/capabilities')).json()
  await page.goto('/')
  if (runtime.needs_setup) {
    await page.getByLabel('Setup token').fill('test-only-bootstrap-for-local-product-browser-suite')
    await page.getByLabel('Full name').fill('Workflow Owner')
  }
  await page.getByLabel('Email', {exact:true}).fill('owner@example.test')
  await page.getByLabel('Password', {exact:true}).fill(workflowPassword)
  await page.getByRole('button', {name:runtime.needs_setup ? 'Create workspace' : 'Sign in',exact:true}).click()
  await expect(page.getByRole('navigation', {name:'Workspace'})).toBeVisible()
  return (await page.request.get('/api/v1/auth/me')).json()
}
export async function writeFact(page: Page, kind:string, id:string, payload:Record<string,unknown>, revision=0) {
  const me = await (await page.request.get('/api/v1/auth/me')).json()
  const response = await page.request.post(`/api/v1/records/${kind}`, {
    headers:{Origin:'http://127.0.0.1:5176','X-CSRF-Token':me.csrf_token,'Idempotency-Key':crypto.randomUUID()},
    data:{record_id:id,expected_revision:revision,source:'Isolated browser workflow fixture',payload},
  })
  expect(response.status(), await response.text()).toBe(201)
  return response.json()
}
export async function workflowCall(page:Page, prefix:string) {
  await writeFact(page,'port',`${prefix}-port`,{name:`${prefix} port`,timezone:'UTC'})
  await writeFact(page,'berth',`${prefix}-berth`,{name:`${prefix} berth`,port_id:`${prefix}-port`})
  await writeFact(page,'vessel',`${prefix}-vessel`,{name:`${prefix} vessel`})
  await writeFact(page,'call',`${prefix}-call`,{vessel_id:`${prefix}-vessel`,berth_id:`${prefix}-berth`,eta:'2026-10-03T10:00:00Z',etd:'2026-10-03T14:00:00Z'})
  await page.reload()
}
