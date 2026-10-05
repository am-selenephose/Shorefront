import {expect, test} from '@playwright/test'
import {workflowSession, workflowCall} from './workflow-fixture'

test('decision history reaches every packet and searches beyond the first page', async ({page}, testInfo) => {
  test.setTimeout(90000)
  const session = await workflowSession(page)
  const prefix = `decision-history-${crypto.randomUUID()}`
  await workflowCall(page, prefix)
  const packets:{id:string;question:string}[] = []
  for (let i=0;i<103;i++) {
    const question = `${prefix} question ${i}`
    const response = await page.request.post('/api/v1/decisions', {
      headers:{Origin:'http://127.0.0.1:5176','X-CSRF-Token':session.csrf_token,'Idempotency-Key':crypto.randomUUID()},
      data:{call_id:`${prefix}-call`,question},
    })
    expect(response.status()).toBe(201)
    packets.push(await response.json())
  }
  await page.goto('/#recovery')
  const history = page.getByRole('region',{name:'Decision history'})
  await history.getByLabel('Search decision history').fill(prefix)
  await history.getByRole('button',{name:'Search packets',exact:true}).click()
  const seen:string[] = []
  for (let i=0;i<5;i++) {
    await expect(history.getByRole('status')).toContainText(`Page ${i+1}`)
    await expect(history.getByRole('status')).not.toContainText('Loading')
    seen.push(...await page.locator('.product-packet h2').allTextContents())
    if (i<4) await history.getByRole('button',{name:'Next page',exact:true}).click()
  }
  for (const packet of packets) expect(seen).toContain(packet.question)
  expect(new Set(seen).size).toBe(seen.length)
  await expect(history.getByRole('button',{name:'Next page',exact:true})).toBeDisabled()
  await history.getByRole('button',{name:'Previous page',exact:true}).click()
  await expect(history.getByRole('status')).toContainText('Page 4')
  const wanted = [...packets].sort((a,b)=>a.id.localeCompare(b.id)).at(-1)!
  await history.getByLabel('Search decision history').fill(wanted.id)
  await history.getByRole('button',{name:'Search packets',exact:true}).click()
  await expect(history.getByRole('status')).toContainText('Page 1')
  await expect(page.locator('.product-packet h2')).toHaveText([wanted.question])
  await page.getByRole('button',{name:'Review packet',exact:true}).click()
  await expect(page.getByText('Input fingerprint:',{exact:false})).toBeVisible()
  await history.getByLabel('Decision status').selectOption('approved')
  await history.getByRole('button',{name:'Search packets',exact:true}).click()
  await expect(page.getByRole('heading',{name:'No matching decisions.'})).toBeVisible()
  await history.getByLabel('Decision status').selectOption('pending')
  await history.getByRole('button',{name:'Search packets',exact:true}).click()
  await expect(page.locator('.product-packet h2')).toHaveText([wanted.question])
  await page.setViewportSize({width:375,height:850})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:testInfo.outputPath('decision-history-mobile.png'),fullPage:true})
})

test('failed history loads retain the last page and recover without false empty success', async ({page}) => {
  const session=await workflowSession(page)
  const prefix=`retry-history-${crypto.randomUUID()}`
  await workflowCall(page,prefix)
  for(let i=0;i<26;i++) {
    const response=await page.request.post('/api/v1/decisions',{
      headers:{Origin:'http://127.0.0.1:5176','X-CSRF-Token':session.csrf_token,'Idempotency-Key':crypto.randomUUID()},
      data:{call_id:`${prefix}-call`,question:`${prefix} ${i}`},
    })
    expect(response.status()).toBe(201)
  }
  let fail = true
  await page.route('**/api/v1/decisions?*', async route => {
    if (fail) return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'History temporarily unavailable'})})
    return route.continue()
  })
  await page.goto('/#recovery')
  await expect(page.getByRole('alert')).toContainText('History temporarily unavailable')
  await expect(page.getByRole('heading',{name:'No decisions recorded yet.'})).toHaveCount(0)
  fail=false
  await page.getByRole('button',{name:'Retry decision history',exact:true}).click()
  await expect(page.getByRole('region',{name:'Decision history'}).getByRole('status')).toContainText('Page 1')
  await expect(page.locator('.product-packet').first()).toBeVisible()
  const firstPage = await page.locator('.product-packet h2').allTextContents()
  fail=true
  await page.getByRole('button',{name:'Next page',exact:true}).click()
  await expect(page.getByRole('alert')).toContainText('History temporarily unavailable')
  expect(await page.locator('.product-packet h2').allTextContents()).toEqual(firstPage)
  await expect(page.getByRole('region',{name:'Decision history'}).getByRole('status')).toContainText('Page 1')
  fail=false
  await page.getByRole('button',{name:'Retry decision history',exact:true}).click()
  await expect(page.getByRole('region',{name:'Decision history'}).getByRole('status')).toContainText('Page 2')
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('a delayed search cannot replace the most recently selected history filter', async ({page}) => {
  await workflowSession(page)
  await page.goto('/#recovery')
  const history=page.getByRole('region',{name:'Decision history'})
  await expect(history.getByRole('status')).toContainText('Page 1')
  let release!:()=>void
  const held=new Promise<void>(resolve=>{release=resolve})
  let observed!:()=>void
  const started=new Promise<void>(resolve=>{observed=resolve})
  let delivered!:()=>void
  const finished=new Promise<void>(resolve=>{delivered=resolve})
  await page.route('**/api/v1/decisions?*',async route=>{
    if(new URL(route.request().url()).searchParams.get('q')!=='delayed-history')return route.continue()
    const response=await route.fetch()
    observed()
    await held
    try {await route.fulfill({response})} finally {delivered()}
  })
  await history.getByLabel('Search decision history').fill('delayed-history')
  await history.getByRole('button',{name:'Search packets',exact:true}).click()
  await started
  try {
    await history.getByLabel('Search decision history').fill('newest-history')
    await history.getByRole('button',{name:'Search packets',exact:true}).click()
    await expect(history.getByRole('status')).toContainText('Search: newest-history')
  } finally {release()}
  await finished
  await expect(history.getByRole('status')).toContainText('Search: newest-history')
  await expect(history.getByRole('status')).not.toContainText('delayed-history')
})
