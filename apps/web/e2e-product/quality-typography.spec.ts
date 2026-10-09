import {expect,test} from '@playwright/test'

for(const viewport of [{width:1440,height:900},{width:390,height:844},{width:320,height:568}]){
  test('operator typography and Quay controls remain legible at '+viewport.width+'px',async({page},testInfo)=>{
    await page.setViewportSize(viewport)
    await page.goto('/?showcase=1#plan')
    const quay=page.getByRole('region',{name:'Quay berth planning board'})
    await expect(quay).toBeVisible()
    const fonts=await page.evaluate(()=>{
      const selectors=['.product-index','.quay-expand-button','.ops-berth-label b','.ops-berth-label small','.ops-timeline-call b']
      return Object.fromEntries(selectors.map(selector=>{
        const target=document.querySelector(selector)
        return [selector,target?parseFloat(getComputedStyle(target).fontSize):null]
      }))
    })
    for(const [selector,size] of Object.entries(fonts)){
      expect(size,selector+' must be present').not.toBeNull()
      expect(size!,selector+' must be readable').toBeGreaterThanOrEqual(14)
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(2)
    await quay.getByRole('button',{name:'Full screen quay'}).click()
    await expect(quay).toHaveAttribute('data-quay-expanded','true')
    await expect(quay.getByRole('button',{name:'Exit full screen quay'})).toBeInViewport()
    await quay.getByRole('button',{name:'Exit full screen quay'}).click()
    await page.getByRole('button',{name:'Dark mode',exact:true}).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
    const darkBody=await page.locator('.product-shell').evaluate(el=>getComputedStyle(el).backgroundColor)
    expect(darkBody).not.toBe('rgba(0, 0, 0, 0)')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(2)
    await page.screenshot({path:testInfo.outputPath('quality-'+viewport.width+'px-dark.png'),fullPage:false})
  })
}
