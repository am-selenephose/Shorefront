import {expect,test} from '@playwright/test'

test('harbor geographic and schematic views can fill the screen and exit without losing map controls',async({page},testInfo)=>{
  await page.setViewportSize({width:1440,height:900})
  await page.goto('/?showcase=1#pulse')
  const map=page.getByRole('region',{name:'Operational geographic harbor map'})
  await expect(map).toBeVisible()
  const fullscreen=map.getByRole('button',{name:'Full screen map'})
  await expect(fullscreen).toBeVisible()
  await fullscreen.click()
  await expect(map).toHaveAttribute('data-map-expanded','true')
  await expect(map.getByRole('button',{name:'Exit full screen map'})).toBeVisible()
  await expect(map.getByRole('group',{name:'Map layers'})).toBeVisible()
  await expect(map.getByText('Berth-linked calls, not live AIS positions.')).toBeVisible()
  const bounds=await map.boundingBox()
  expect(bounds).not.toBeNull()
  // Native fullscreen can resize the viewport to the runner's actual display.
  // Verify complete viewport coverage instead of assuming a 1440px monitor.
  const viewport=await page.evaluate(()=>({width:window.innerWidth,height:window.innerHeight}))
  expect(bounds!.x).toBeGreaterThanOrEqual(-1)
  expect(bounds!.x).toBeLessThanOrEqual(1)
  expect(bounds!.y).toBeGreaterThanOrEqual(-1)
  expect(bounds!.y).toBeLessThanOrEqual(1)
  expect(bounds!.width).toBeGreaterThanOrEqual(viewport.width-2)
  expect(bounds!.height).toBeGreaterThanOrEqual(viewport.height-2)
  await page.screenshot({path:testInfo.outputPath('fullscreen-map-desktop.png')})
  await page.keyboard.press('Escape')
  await expect(map).toHaveAttribute('data-map-expanded','false')
  await expect(fullscreen).toBeVisible()
  const compact=await map.boundingBox()
  expect(compact!.height).toBeLessThan(650)
})

test('mobile fullscreen map provides an Escape/Exit path when browser Fullscreen API is restricted',async({page},testInfo)=>{
  await page.addInitScript(()=>{
    Object.defineProperty(Element.prototype,'requestFullscreen',{configurable:true,value:undefined})
    const getContext=HTMLCanvasElement.prototype.getContext
    Object.defineProperty(HTMLCanvasElement.prototype,'getContext',{
      configurable:true,
      value:function(this:HTMLCanvasElement,kind:string,...options:unknown[]){
        if(kind==='webgl2')return null
        return Reflect.apply(getContext,this,[kind,...options])
      }
    })
  })
  await page.setViewportSize({width:390,height:844})
  await page.goto('/?showcase=1#coordination')
  const map=page.getByRole('region',{name:'Operational geographic harbor map'})
  await expect(map).toBeVisible()
  // Coordination sits below the fold on a phone. Scroll vertically first,
  // then verify the first toolbar action is visible without horizontal panning.
  await map.getByRole('button',{name:'Full screen map'}).scrollIntoViewIfNeeded()
  await expect(map.getByRole('button',{name:'Full screen map'})).toBeInViewport()
  await expect(map.locator('.product-map-layers')).toHaveJSProperty('scrollLeft',0)
  await map.getByRole('button',{name:'Full screen map'}).click()
  await expect(map).toHaveAttribute('data-map-expanded','true')
  await expect(map.getByRole('region',{name:'Schematic berth digital twin'})).toBeVisible()
  await expect(map.getByRole('button',{name:'Exit full screen map'})).toBeVisible()
  const bounds=await map.boundingBox()
  expect(bounds!.width).toBeGreaterThanOrEqual(388)
  expect(bounds!.height).toBeGreaterThanOrEqual(840)
  await page.screenshot({path:testInfo.outputPath('fullscreen-map-mobile.png')})
  await map.getByRole('button',{name:'Exit full screen map'}).click()
  await expect(map).toHaveAttribute('data-map-expanded','false')
  await map.getByRole('button',{name:'Full screen map'}).click()
  await page.keyboard.press('Escape')
  await expect(map).toHaveAttribute('data-map-expanded','false')
})
