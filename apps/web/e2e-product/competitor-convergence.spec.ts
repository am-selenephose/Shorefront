import {expect,test} from '@playwright/test'

test('Pulse converges lineup, resources, events and human decision context into one operations deck', async ({page}) => {
  await page.setViewportSize({width:1440,height:1100})
  await page.goto('/?showcase=1#pulse')

  const deck=page.getByRole('region',{name:'Integrated operations deck'})
  await expect(deck).toBeVisible()
  await expect(page.getByRole('region',{name:'Operational lineup'})).toContainText('MV Aurora')
  await expect(page.getByRole('region',{name:'Operational lineup'})).toContainText('Pacific Meridian')
  await expect(page.getByRole('region',{name:'Resource lanes'})).toContainText('Tug 14')
  await expect(page.getByRole('region',{name:'Operational event scrubber'})).toContainText('SIMULATED SOURCE')
  await expect(page.getByRole('region',{name:'Operator decision lane'})).toContainText('Review selected-call incident')
  await expect(page.getByRole('region',{name:'Operator decision lane'})).toContainText('Operator / supervisor remains in control')

  await page.getByRole('button',{name:'Needs attention',exact:true}).click()
  const lineup=page.getByRole('region',{name:'Operational lineup'})
  await expect(lineup).toContainText('MV Aurora')
  await expect(lineup).not.toContainText('Pacific Meridian')
  await expect(lineup).not.toContainText('Northstar Atlas')

  await page.getByRole('button',{name:'All',exact:true}).click()
  await page.getByLabel('Search operating picture').fill('Pacific')
  await expect(lineup).toContainText('Pacific Meridian')
  await expect(lineup).not.toContainText('MV Aurora')

  await page.getByRole('button',{name:'6H',exact:true}).last().click()
  await expect(page.getByRole('button',{name:'6H',exact:true}).last()).toHaveAttribute('aria-pressed','true')
})

test('integrated operations deck remains page-contained on mobile', async ({page}) => {
  await page.setViewportSize({width:390,height:844})
  await page.goto('/?showcase=1#pulse')
  await expect(page.getByRole('region',{name:'Integrated operations deck'})).toBeVisible()
  const geometry=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,innerWidth}))
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.innerWidth)
})
