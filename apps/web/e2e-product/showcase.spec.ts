import {expect, test} from '@playwright/test'
import {expectGeographicMapRenderer} from './map-capability'

test('public showcase is data-rich, read-only and isolated from operational data', async ({page}) => {
  const privateApiRequests:string[] = []
  const legacyOsmRequests:string[] = []
  const mapProviderFailures:{status:number;url:string}[] = []
  const mapProviderResponses:{status:number;url:string}[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/') && url.pathname !== '/api/v1/runtime/capabilities') {
      privateApiRequests.push(url.pathname)
    }
    if (url.hostname === 'tile.openstreetmap.org') legacyOsmRequests.push(url.href)
  })
  page.on('response', response => {
    const url = new URL(response.url())
    if (url.hostname === 'tiles.openfreemap.org') {
      mapProviderResponses.push({status:response.status(),url:url.href})
      if (response.status() >= 400) mapProviderFailures.push({status:response.status(),url:url.href})
    }
  })

  await page.goto('/?showcase=1')
  await expect(page.getByText('SIMULATED DEMO · READ ONLY', {exact:true}).first()).toBeVisible()
  await expect(page.getByText('Northstar Container Harbor', {exact:true}).first()).toBeVisible()
  await expect(page.getByText('MV Aurora', {exact:true}).first()).toBeVisible()
  await expect(page.getByText('Tug 14 unavailable', {exact:true}).first()).toBeVisible()
  await expect(page.getByRole('navigation', {name:'Showcase workspaces'})).toBeVisible()
  await expect(page.locator('.product-boundary')).toContainText('Simulated operational picture.')
  await expect(page.locator('.product-boundary')).not.toContainText('Real operational mode.')
  const geographicMap=page.getByRole('region',{name:'Operational geographic harbor map'})
  await expect(geographicMap).toBeVisible()
  const webgl2=await expectGeographicMapRenderer(page,geographicMap)
  if(webgl2){
    await expect.poll(()=>mapProviderResponses.length).toBeGreaterThan(0)
    expect(await geographicMap.locator('.product-map-berth-marker').count()).toBeGreaterThanOrEqual(2)
  }else{
    expect(mapProviderResponses).toEqual([])
    await expect(geographicMap.getByRole('region',{name:'Schematic berth digital twin'})).toContainText('North Quay')
  }
  await expect(page.getByText('SIMULATED HARBOR OVERVIEW', {exact:true})).toHaveCount(0)
  await expect(geographicMap.getByText('Port geography is not configured.', {exact:true})).toHaveCount(0)
  expect(legacyOsmRequests).toEqual([])
  expect(mapProviderFailures).toEqual([])

  await page.getByRole('link', {name:'Plan', exact:true}).click()
  await expect(page.locator('[data-product-workspace="plan"]')).toContainText('North Quay')
  await expect(page.locator('[data-product-workspace="plan"]')).toContainText('MV Aurora')

  await page.getByRole('link', {name:'Calls', exact:true}).click()
  await expect(page.locator('[data-product-workspace="calls"]')).toContainText('Pacific Meridian')

  await page.getByRole('link', {name:'Exceptions', exact:true}).click()
  await expect(page.locator('[data-product-workspace="exceptions"]')).toContainText('Tug 14 unavailable')

  await page.getByRole('link', {name:'Coordination', exact:true}).click()
  const coordinationVisual=page.getByRole('region',{name:'Coordination visual context'})
  await expect(coordinationVisual).toBeVisible()
  await expect(coordinationVisual).toContainText('Responsibility graph')
  await expect(coordinationVisual).toContainText('Open coordination deadlines')
  expect(await coordinationVisual.locator('.coord-network-line').count()).toBeGreaterThan(0)
  expect(await coordinationVisual.locator('.coord-party-line').count()).toBeGreaterThan(0)

  await page.getByRole('link', {name:'Recovery', exact:true}).click()
  await expect(page.getByRole('heading', {name:'Compare recovery paths before a human decides.'})).toBeVisible()
  await expect(page.getByText('Option A · Reassign Tug 08', {exact:true})).toBeVisible()

  await page.getByRole('link', {name:'Evidence', exact:true}).click()
  await expect(page.getByRole('heading', {name:'Every demo decision keeps its context.'})).toBeVisible()
  await expect(page.getByText('SIMULATED SOURCE', {exact:true}).first()).toBeVisible()

  await page.setViewportSize({width:390,height:844})
  await page.goto('/?showcase=1#pulse')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.getByRole('navigation', {name:'Showcase workspaces'})).toBeVisible()

  expect(privateApiRequests).toEqual([])

  await page.getByRole('link', {name:'Return to sign in'}).first().click()
  await expect(page.getByLabel('Email',{exact:true})).toBeVisible()
  await expect(page).not.toHaveURL(/showcase=1/)
})
