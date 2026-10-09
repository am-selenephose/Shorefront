import {expect,test} from '@playwright/test'

test('operator map zoom survives call selection, theme changes and layer toggles',async({page},testInfo)=>{
  await page.setViewportSize({width:1440,height:940})
  await page.goto('/?showcase=1#pulse')
  const berthMarkers=page.locator('.product-map-berth-marker')
  const unavailable=page.getByRole('status',{name:'Geographic map unavailable'})
  await expect.poll(async()=>await berthMarkers.count()===2 || await unavailable.isVisible(),{timeout:15000}).toBeTruthy()
  if(await unavailable.isVisible()) {
    // Firefox/CI may lack WebGL2. Validate the explicit, non-geographic
    // fallback and preserve operational controls rather than invent markers.
    const schematic=page.getByRole('region',{name:'Schematic berth digital twin'})
    await expect(schematic).toBeVisible()
    await expect(schematic.getByText('North Quay')).toBeVisible()
    await page.locator('.ops-runway-select').nth(1).click()
    await expect(page.locator('.ops-call-focus h3')).toContainText('Northstar Atlas')
    await expect(schematic.locator('.product-map-schematic-lane.is-focused')).toContainText('Northstar Atlas')
    await page.getByRole('button',{name:'Dark mode',exact:true}).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
    const layers=page.getByRole('group',{name:'Map layers'})
    await layers.getByRole('button',{name:'Exceptions only'}).click()
    await expect(layers.getByRole('button',{name:'Exceptions only'})).toHaveAttribute('aria-pressed','true')
    await page.screenshot({path:testInfo.outputPath('operator-map-degraded-schematic-retained.png')})
    return
  }
  await expect(berthMarkers).toHaveCount(2)
  const separation=()=>page.evaluate(()=>{
    const markers=[...document.querySelectorAll('.product-map-berth-marker')].map(node=>node.getBoundingClientRect())
    if(markers.length!==2)return 0
    return Math.hypot(markers[0].x-markers[1].x,markers[0].y-markers[1].y)
  })
  const baseline=await separation()
  expect(baseline).toBeGreaterThan(25)
  const zoom=page.locator('.maplibregl-ctrl-zoom-in')
  await expect(zoom).toBeVisible()
  await zoom.click()
  await zoom.click()
  await zoom.click()
  await expect.poll(separation,{timeout:7000}).toBeGreaterThan(baseline*1.8)
  const zoomed=await separation()

  await page.locator('.ops-runway-select').nth(1).click()
  await expect(page.locator('.ops-call-focus h3')).toContainText('Northstar Atlas')
  await expect.poll(separation).toBeGreaterThan(zoomed*.93)

  await page.getByRole('button',{name:'Dark mode',exact:true}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
  await expect.poll(separation).toBeGreaterThan(zoomed*.93)

  const layers=page.getByRole('group',{name:'Map layers'})
  await layers.getByRole('button',{name:'Exceptions only'}).click()
  await expect.poll(separation).toBeGreaterThan(zoomed*.93)

  await page.screenshot({path:testInfo.outputPath('operator-map-camera-retained.png')})
})

test("geographic WebGL failure retains a truthful schematic and operator controls",async({page})=>{
  await page.addInitScript(()=>{
    const original=HTMLCanvasElement.prototype.getContext
    Object.defineProperty(HTMLCanvasElement.prototype,"getContext",{
      configurable:true,
      value:function(this:HTMLCanvasElement,kind:string,...options:unknown[]){
        if(kind==="webgl2")return null
        return Reflect.apply(original,this,[kind,...options])
      }
    })
  })
  await page.goto("/?showcase=1#pulse")
  const map=page.getByRole("region",{name:"Operational geographic harbor map"})
  await expect(map.getByRole("status",{name:"Geographic map unavailable"})).toBeVisible()
  await expect(map.locator(".product-map-berth-marker")).toHaveCount(0)
  const schematic=map.getByRole("region",{name:"Schematic berth digital twin"})
  await expect(schematic).toBeVisible()
  await expect(schematic.getByText("North Quay")).toBeVisible()
  await page.locator(".ops-runway-select").nth(1).click()
  await expect(schematic.locator(".product-map-schematic-lane.is-focused")).toContainText("Northstar Atlas")
  await page.getByRole("button",{name:"Dark mode",exact:true}).click()
  await expect(schematic).toBeVisible()
  await map.getByRole("group",{name:"Map layers"}).getByRole("button",{name:"Exceptions only"}).click()
  await expect(map.getByRole("group",{name:"Map layers"}).getByRole("button",{name:"Exceptions only"})).toHaveAttribute("aria-pressed","true")
})
