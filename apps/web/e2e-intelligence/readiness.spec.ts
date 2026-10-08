import {expect,test} from '@playwright/test'

test('authenticated readiness desk analyzes real records with inspectable evidence and action links', async ({page},testInfo)=>{
  const runtime=await (await page.request.get('/api/v1/runtime/capabilities')).json()
  await page.goto(runtime.needs_setup?'/#setup=test-only-bootstrap-for-local-product-browser-suite':'/')
  if(runtime.needs_setup) await page.getByLabel('Full name').fill('Port Owner')
  await page.getByLabel('Email',{exact:true}).fill('owner@example.test')
  await page.getByLabel('Password',{exact:true}).fill('test-only customer passphrase 42')
  await page.getByRole('button',{name:runtime.needs_setup?'Create workspace':'Sign in',exact:true}).click()
  await expect(page.getByRole('link',{name:'Records',exact:true})).toBeVisible()
  const auth=await page.request.get('/api/v1/auth/me')
  expect(auth.status(),await auth.text()).toBe(200)
  const session=await auth.json()
  const headers={Origin:new URL(page.url()).origin,'X-CSRF-Token':session.csrf_token}
  const facts=await (await page.request.get('/api/v1/workspace')).json()
  const already=new Set(facts.records.map((r:{kind:string;record_id:string})=>r.kind+':'+r.record_id))
  for(const [kind,id,payload] of [
    ['port','readiness-port',{name:'Readiness Harbor',timezone:'UTC'}],
    ['berth','readiness-berth',{name:'Eastern Berth',port_id:'readiness-port'}],
    ['vessel','readiness-vessel',{name:'MV Evidence',length_m:185}],
    ['call','readiness-call',{vessel_id:'readiness-vessel',berth_id:'readiness-berth',eta:'2026-11-20T10:00:00Z',etd:'2026-11-20T15:00:00Z'}],
  ] as const){
    if(already.has(kind+':'+id)) continue
    const response=await page.request.post('/api/v1/records/'+kind,{headers:{...headers,'Idempotency-Key':'readiness-'+id},data:{record_id:id,expected_revision:0,source:'Operator verified timetable',payload}})
    expect(response.status(),await response.text()).toBe(201)
  }
  await page.goto('/#readiness')
  await expect(page.getByRole('heading',{name:'Know what is recorded. See what is missing.'})).toBeVisible()
  await expect(page.getByRole('region',{name:'Operational readiness intelligence'})).toContainText('MV Evidence')
  await page.getByRole('button',{name:/MV Evidence/}).click()
  await expect(page.getByRole('region',{name:'Call evidence review'})).toContainText('Geographic berth position')
  await expect(page.getByRole('region',{name:'Call evidence review'})).toContainText('Operator verified timetable')
  await page.getByRole('button',{name:'Missing coverage'}).click()
  await expect(page.getByRole('region',{name:'Call evidence review'})).toContainText('Recorded berth / vessel dimensions')
  await page.screenshot({path:testInfo.outputPath('real-operational-readiness.png'),fullPage:true})
  await page.setViewportSize({width:390,height:844})
  await expect(page.getByRole('region',{name:'Operational readiness intelligence'})).toBeVisible()
  const horizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)
  expect(horizontalOverflow,'Mobile page must not overflow horizontally').toBeLessThanOrEqual(2)
  await page.screenshot({path:testInfo.outputPath('readiness-mobile.png'),fullPage:true})
  await page.getByRole('button',{name:'Switch to dark mode'}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
  const nightHero=await page.locator('.readiness-hero').evaluate(node=>getComputedStyle(node).backgroundImage)
  expect(nightHero).toContain('radial-gradient')
  await expect.poll(()=>page.locator('.product-sidebar nav a[aria-current="page"]').evaluate(node=>getComputedStyle(node).borderLeftColor)).toBe('rgb(254, 175, 119)')
  await page.keyboard.press('Control+k')
  await expect(page.getByLabel('Global workspace search')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByLabel('Global workspace search')).not.toBeFocused()
  await page.screenshot({path:testInfo.outputPath('readiness-night-mobile.png'),fullPage:true})

})
