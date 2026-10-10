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
