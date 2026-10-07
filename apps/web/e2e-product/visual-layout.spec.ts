import {expect,test} from '@playwright/test'
import {expectGeographicMapRenderer} from './map-capability'

test('coordination responsibility graph stays inside its visual panel at desktop width', async ({page}) => {
  await page.setViewportSize({width:1440,height:1000})
  await page.goto('/?showcase=1#coordination')
  const panel=page.locator('.coord-network-visual')
  await expect(panel).toBeVisible()
  const geometry=await panel.evaluate((node)=>{
    const panel=node.getBoundingClientRect()
    const parties=[...node.querySelectorAll('.coord-thread-party')].map(item=>item.getBoundingClientRect())
    return {
      panelRight:panel.right,
      maxPartyRight:Math.max(panel.left,...parties.map(rect=>rect.right)),
      scrollWidth:(node as HTMLElement).scrollWidth,
      clientWidth:(node as HTMLElement).clientWidth,
    }
  })
  expect(geometry.maxPartyRight).toBeLessThanOrEqual(geometry.panelRight+1)
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth+1)
})

test('mobile berth horizon has an explicit horizontal scroll viewport instead of clipping the timeline', async ({page}) => {
  await page.setViewportSize({width:390,height:844})
  await page.goto('/?showcase=1#pulse')
  const horizon=page.getByRole('region',{name:'Port operating horizon'})
  await expect(horizon).toBeVisible()
  const scroller=horizon.locator('.ops-horizon-scroll')
  await expect(scroller).toBeVisible()
  const state=await scroller.evaluate(node=>{
    const el=node as HTMLElement
    const style=getComputedStyle(el)
    return {overflowX:style.overflowX,scrollWidth:el.scrollWidth,clientWidth:el.clientWidth}
  })
  expect(['auto','scroll']).toContain(state.overflowX)
  expect(state.scrollWidth).toBeGreaterThan(state.clientWidth)
})


test('mobile coordination keeps party ownership readable rather than crushing the responsibility column', async ({page}) => {
  await page.setViewportSize({width:390,height:844})
  await page.goto('/?showcase=1#coordination')
  const parties=page.locator('.coord-party-node')
  await expect(parties.first()).toBeVisible()
  const widths=await parties.evaluateAll(nodes=>nodes.map(node=>node.getBoundingClientRect().width))
  expect(Math.min(...widths)).toBeGreaterThan(90)
})

test('public operating system stays readable and inside the viewport across workspaces', async ({page}) => {
  const views=['pulse','plan','calls','exceptions','coordination','recovery','evidence']
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:width===390?844:1000})
    for(const view of views){
      await page.goto('/?showcase=1#'+view)
      await expect(page.getByRole('link',{name:view[0].toUpperCase()+view.slice(1),exact:true})).toHaveAttribute('aria-current','page')
      await page.evaluate(()=>{document.documentElement.dataset.theme='light'})
      const audit=await page.evaluate(()=>{
        const tiny:{tag:string;className:string;text:string;size:number}[]=[]
        for(const el of document.querySelectorAll('.product-shell *')){
          if(el.closest('.maplibregl-control-container')) continue
          const own=[...el.childNodes].filter(node=>node.nodeType===Node.TEXT_NODE).map(node=>node.textContent??'').join('').trim()
          if(!own) continue
          const rect=el.getBoundingClientRect()
          const style=getComputedStyle(el)
          if(rect.width<1||rect.height<1||style.display==='none'||style.visibility==='hidden') continue
          const size=parseFloat(style.fontSize)
          if(Number.isFinite(size)&&size<10) tiny.push({tag:el.tagName,className:String(el.className),text:own.slice(0,60),size})
        }
        return {scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth,tiny}
      })
      expect(audit.scrollWidth,view+' '+width+'px page width').toBeLessThanOrEqual(audit.viewport)
      expect(audit.tiny,view+' '+width+'px tiny visible text').toEqual([])
    }
  }
  await page.setViewportSize({width:1440,height:1000})
  await page.goto('/?showcase=1#pulse')
  const geographicMap=page.getByRole('region',{name:'Operational geographic harbor map'})
  const webgl2=await expectGeographicMapRenderer(page,geographicMap)
  if(webgl2) await expect(page.locator('.product-geographic-map .maplibregl-ctrl-attrib-inner')).toContainText('OpenFreeMap')
  else await expect(geographicMap.getByRole('region',{name:'Schematic berth digital twin'})).toBeVisible()
})

test('recovery and evidence surfaces expose decision context instead of dead demo space', async ({page}) => {
  await page.setViewportSize({width:1440,height:1000})
  await page.goto('/?showcase=1#recovery')
  await expect(page.getByRole('region',{name:'Recovery dependency chain'})).toBeVisible()
  await expect(page.getByRole('region',{name:'Affected call runway'})).toBeVisible()
  await expect(page.getByLabel('Decision context summary')).toContainText('Human')

  await page.goto('/?showcase=1#evidence')
  await expect(page.getByRole('region',{name:'Simulated source disagreement'})).toBeVisible()
  await expect(page.getByRole('region',{name:'Simulated audit lineage'})).toBeVisible()
  await expect(page.getByLabel('Evidence context summary')).toContainText('OPEN CONFLICTS')
})
