import {expect,test} from '@playwright/test'

test('coordination displays linked berth and call visual before the geographic map bundle finishes loading',async ({page})=>{
  await page.route('**/assets/ProductHarborMap-*.js',async route=>{
    await new Promise(resolve=>setTimeout(resolve,10000))
    await route.continue()
  })
  await page.goto('/?showcase=1#coordination',{waitUntil:'domcontentloaded'})
  const visual=page.getByRole('region',{name:'Coordination visual context'})
  const preview=visual.getByRole('status',{name:'Harbor map loading preview'})
  await expect(preview).toBeVisible({timeout:2500})
  await expect(preview.getByText('SCHEMATIC · NOT GEOGRAPHIC',{exact:true})).toBeVisible()
  await expect(preview.getByText('North Quay',{exact:true})).toBeVisible()
  await expect(preview.locator('.coord-map-preview-vessels').getByText('MV Aurora',{exact:false})).toBeVisible()
  await expect(preview.locator('.coord-map-preview-vessels').getByText('Pacific Meridian',{exact:false})).toBeVisible()
  await expect(visual.getByText('Responsibility graph · CALL → THREAD → PARTY')).toBeVisible()
  await expect(visual.getByRole('region',{name:'Operational geographic harbor map'})).toBeVisible({timeout:16000})
})
