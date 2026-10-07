import {expect,type Locator,type Page} from '@playwright/test'

export async function expectGeographicMapRenderer(page:Page,map:Locator):Promise<boolean>{
  const webgl2=await page.evaluate(()=>{
    try{
      const canvas=document.createElement('canvas')
      const context=canvas.getContext('webgl2')
      const supported=Boolean(context)
      context?.getExtension('WEBGL_lose_context')?.loseContext()
      return supported
    }catch{return false}
  })
  if(webgl2){
    await expect(map.locator('.maplibregl-canvas')).toBeVisible()
    await expect(map.getByRole('status',{name:'Geographic map unavailable'})).toHaveCount(0)
    return true
  }else{
    await expect(map.locator('.maplibregl-canvas')).toHaveCount(0)
    await expect(map.getByRole('status',{name:'Geographic map unavailable'})).toContainText('WebGL2')
    return false
  }
}
