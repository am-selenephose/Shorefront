import {expect,test} from '@playwright/test'

test('night console preserves warm amber interaction hierarchy across desktop and mobile',async({page},testInfo)=>{
  await page.setViewportSize({width:1536,height:1000})
  await page.goto('/?showcase=1#pulse')
  const map=page.getByRole('region',{name:'Port operations command center'})
  await expect(map).toBeVisible()
  await page.getByRole('button',{name:'Dark mode',exact:true}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
  await expect(page.locator('.ops-horizon-switch button.active')).toBeVisible()
  await page.screenshot({path:testInfo.outputPath('night-before.png'),fullPage:true})
  const night=await page.evaluate(()=>{
    const css=(selector:string,property:string)=>{const node=document.querySelector(selector);return node?getComputedStyle(node).getPropertyValue(property).trim():''}
    return {
      activeBerth:css('.ops-horizon-switch button.active','background-color'),
      activeNavigation:css('.showcase-shell nav a[aria-current="page"]','border-left-color'),
      mapSurface:css('.ops-horizon-track','background-image'),
      focusPanel:css('.ops-call-focus','background-image'),
      background:css('.product-shell','background-color'),
      indicator:css('.ops-horizon-call.is-focused','box-shadow'),
    }
  })
  expect(night.activeBerth).toBe('rgb(254, 175, 119)')
  expect(night.activeNavigation).toBe('rgb(254, 175, 119)')
  expect(night.mapSurface).toContain('gradient')
  expect(night.focusPanel).toContain('gradient')
  expect(night.indicator).not.toBe('none')
  await page.setViewportSize({width:390,height:844})
  await expect(map).toBeVisible()
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)
  expect(overflow).toBeLessThanOrEqual(2)
  await page.screenshot({path:testInfo.outputPath('night-mobile.png'),fullPage:true})
  await page.getByRole('button',{name:'Light mode',exact:true}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','light')
  const light=await page.locator('.ops-horizon-switch button.active').evaluate(element=>getComputedStyle(element).backgroundColor)
  expect(light).toBe('rgb(254, 175, 119)')
})
