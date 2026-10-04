import {expect, test} from '@playwright/test'

test('public showcase is data-rich, read-only and isolated from operational data', async ({page}) => {
  const privateApiRequests:string[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/') && url.pathname !== '/api/v1/runtime/capabilities') {
      privateApiRequests.push(url.pathname)
    }
  })

  await page.goto('/?showcase=1')
  await expect(page.getByText('SIMULATED DEMO · READ ONLY', {exact:true}).first()).toBeVisible()
  await expect(page.locator('h1').filter({hasText:'Northstar Container Harbor'})).toBeVisible()
  await expect(page.getByText('MV Aurora', {exact:true}).first()).toBeVisible()
  await expect(page.getByText('Tug 14 unavailable', {exact:true}).first()).toBeVisible()
  await expect(page.getByRole('navigation', {name:'Showcase workspaces'})).toBeVisible()

  await page.getByRole('link', {name:'Plan', exact:true}).click()
  await expect(page.locator('[data-product-workspace="plan"]')).toContainText('North Quay')
  await expect(page.locator('[data-product-workspace="plan"]')).toContainText('MV Aurora')

  await page.getByRole('link', {name:'Calls', exact:true}).click()
  await expect(page.locator('[data-product-workspace="calls"]')).toContainText('Pacific Meridian')

  await page.getByRole('link', {name:'Exceptions', exact:true}).click()
  await expect(page.locator('[data-product-workspace="exceptions"]')).toContainText('Tug 14 unavailable')

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
