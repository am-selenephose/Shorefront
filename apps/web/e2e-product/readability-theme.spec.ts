import {expect,test} from '@playwright/test'

test('light mode preserves the coastal palette and a 13px readable text floor', async ({page}) => {
  await page.setViewportSize({width:1600,height:1000})
  await page.goto('/?showcase=1#pulse')
  await expect(page.getByRole('heading',{name:'Your port. Your operational record.'})).toBeVisible()

  const audit=await page.evaluate(()=>{
    const root=getComputedStyle(document.documentElement)
    const vars=Object.fromEntries(
      ['--cream','--teal','--sunlight','--peach','--background','--surface','--surface-deep']
        .map(key=>[key,root.getPropertyValue(key).trim()])
    )
    const belowFloor:{tag:string;className:string;text:string;size:number}[]=[]
    for(const el of document.querySelectorAll('.product-shell *')){
      if(el.closest('.maplibregl-control-container')) continue
      const own=[...el.childNodes]
        .filter(node=>node.nodeType===Node.TEXT_NODE)
        .map(node=>node.textContent??'')
        .join('')
        .trim()
      if(!own) continue
      const style=getComputedStyle(el)
      if(style.display==='none'||style.visibility==='hidden'||Number(style.opacity)===0) continue
      const rect=el.getBoundingClientRect()
      if(rect.width<1||rect.height<1) continue
      const size=parseFloat(style.fontSize)
      if(Number.isFinite(size)&&size<13){
        belowFloor.push({tag:el.tagName,className:String(el.className),text:own.slice(0,80),size})
      }
    }
    const panelHeader=document.querySelector('.product-shell .ops-panel>header')
    const selectedCall=document.querySelector('.ops-runway-row.is-selected')
    return {
      theme:document.documentElement.dataset.theme||'light',
      vars,
      belowFloor,
      panelHeaderBackground:panelHeader?getComputedStyle(panelHeader).backgroundColor:'',
      selectedCallBackground:selectedCall?getComputedStyle(selectedCall).backgroundColor:'',
    }
  })

  expect(audit.theme).toBe('light')
  expect(audit.vars).toEqual({
    '--cream':'#eceac1',
    '--teal':'#64989a',
    '--sunlight':'#fed987',
    '--peach':'#feaf77',
    '--background':'#eceac1',
    '--surface':'#f7f5e3',
    '--surface-deep':'#e4e3bc',
  })
  expect(audit.belowFloor).toEqual([])
  expect(audit.panelHeaderBackground).toBe('rgb(247, 245, 227)')
  expect(audit.selectedCallBackground).toBe('rgb(251, 225, 197)')
})
