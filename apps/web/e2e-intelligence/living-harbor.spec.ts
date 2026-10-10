import {expect,test} from '@playwright/test'
const demo='/?showcase=1&living=1#overview'
test('Living Harbor has eight functioning workspaces',async({page})=>{
 const errors:string[]=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.goto(demo)
 await expect(page.getByTestId('living-harbor')).toBeVisible()
 const nav=page.getByRole('navigation',{name:'Living Harbor workspaces'})
 const names=['Overview','Port Calls','Berth Planning','Resources','Operations','Incidents','Reports','Administration']
 await expect(nav.getByRole('link')).toHaveCount(8)
 for(const name of names){
  await nav.getByRole('link',{name,exact:true}).click()
  await expect(nav.getByRole('link',{name,exact:true})).toHaveAttribute('aria-current','page')
  await expect(page.locator('.lh-workspace-layer, .lh-floating-calls').first()).toBeVisible()
 }
 expect(errors).toEqual([])
})
test('selection preserves call identity and source',async({page})=>{
 await page.goto(demo)
 await page.getByRole('region',{name:'Active port calls'}).getByRole('button',{name:/MV Aurora/}).click()
 const inspector=page.getByRole('complementary',{name:/Selected vessel MV Aurora/})
 await expect(inspector).toContainText('North Quay')
 await expect(inspector).toContainText('SIMULATED SOURCE')
 await expect(inspector).toContainText('Illustrative, not geolocated')
 await inspector.getByRole('button',{name:'Close vessel inspector'}).click()
 await expect(inspector).toHaveCount(0)
})
test('violet proposal and ambient controls cause no operational writes',async({page})=>{
 const writes:string[]=[]
 page.on('request',r=>{if(['POST','PUT','PATCH','DELETE'].includes(r.method())&&r.url().includes('/api/v1/'))writes.push(r.url())})
 await page.goto(demo)
 await page.getByRole('button',{name:'Preview proposal'}).click()
 await expect(page.getByRole('status').filter({hasText:'VIOLET SCENARIO PREVIEW'})).toContainText('NOT APPLIED')
 await page.getByRole('button',{name:'Close proposal'}).click()
 await expect(page.getByRole('status').filter({hasText:'VIOLET SCENARIO PREVIEW'})).toHaveCount(0)
 await page.getByRole('button',{name:/^(Pause ambiance|Resume ambiance)$/}).click()
 await expect(page.getByRole('button',{name:/^(Pause ambiance|Resume ambiance)$/})).toBeVisible()
 expect(writes).toEqual([])
})
test('mobile renders accessible schematic and records',async({page})=>{
 await page.setViewportSize({width:390,height:844})
 await page.goto(demo)
 await expect(page.getByText('Schematic fallback')).toBeVisible()
 await expect(page.locator('.lh-workspace-layer')).toBeVisible()
 await expect(page.getByRole('navigation',{name:'Living Harbor workspaces'}).getByRole('link')).toHaveCount(8)
 await expect(page.locator('.lh-world canvas')).toHaveCount(0)
})

test('authenticated Living Harbor uses real workspace and preserves console access',async({page})=>{
 const runtime=await (await page.request.get('/api/v1/runtime/capabilities')).json()
 await page.goto(runtime.needs_setup?'/#setup=test-only-bootstrap-for-local-product-browser-suite':'/')
 if(runtime.needs_setup)await page.getByLabel('Full name').fill('Living Harbor Owner')
 await page.getByLabel('Email',{exact:true}).fill('owner@example.test')
 await page.getByLabel('Password').fill('test-only customer passphrase 42')
 await page.getByRole('button',{name:runtime.needs_setup?'Create workspace':'Sign in',exact:true}).click()
 await expect(page.getByRole('link',{name:'Living Harbor'})).toBeVisible()
 await page.getByRole('link',{name:'Living Harbor'}).click()
 await expect(page.getByTestId('living-harbor')).toBeVisible()
 await expect(page.getByText('OPERATOR RECORDS')).toBeVisible()
 await expect(page.getByText('AUTHENTICATED RECORDS',{exact:false})).toBeVisible()
 await expect(page.getByText('POSITIONS ILLUSTRATIVE')).toBeVisible()
 await expect(page.locator('.lh-sidebar-bottom')).toContainText('REAL RECORDS · NO GEO POSITION')
 await expect(page.locator('.lh-call-list')).not.toContainText('MV Aurora')
 await page.getByRole('navigation',{name:'Living Harbor workspaces'}).getByRole('link',{name:'Reports'}).click()
 await expect(page.getByText('Every number is derived from the authenticated operational record snapshot.')).toBeVisible()
 await page.getByRole('link',{name:/Classic workspace/}).click()
 await expect(page.getByRole('navigation',{name:'Workspace'})).toBeVisible()
})
test('operational Living Harbor requires sign-in and never discloses demo records',async({page})=>{
 await page.goto('/?living=1#overview')
 await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeVisible()
 await expect(page.getByTestId('living-harbor')).toHaveCount(0)
 await expect(page.getByText('MV Aurora',{exact:true})).toHaveCount(0)
})
