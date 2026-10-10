import {expect,test} from '@playwright/test'
import {expectGeographicMapRenderer} from './map-capability'
import {workflowCall,workflowSession} from './workflow-fixture'

test('Pulse composes map, schematic fallback, focused call and berth horizon into one cockpit', async ({page}) => {
  await workflowSession(page)
  await workflowCall(page,'cockpit')
  await page.reload()
  await page.getByRole('link',{name:'Pulse',exact:true}).click()

  const command=page.getByRole('region',{name:'Port operations command center'})
  await expect(command).toBeVisible()
  const cockpit=command.getByRole('region',{name:'Operational decision cockpit'})
  await expect(cockpit).toBeVisible()
  await expect(cockpit.getByRole('heading',{name:'Call focus',exact:true})).toBeVisible()
  await expect(cockpit).toContainText('cockpit vessel')
  await expect(cockpit).toContainText('cockpit berth')

  const horizon=command.getByRole('region',{name:'Port operating horizon'})
  await expect(horizon).toBeVisible()
  for (const label of ['6H','12H','24H','48H']) await expect(horizon.getByRole('button',{name:label,exact:true})).toBeVisible()
  await expect(horizon).toContainText('cockpit vessel')

  const map=command.getByRole('region',{name:'Operational geographic harbor map'})
  await expectGeographicMapRenderer(page,map)
  await expect(map.getByRole('region',{name:'Schematic berth digital twin'}).getByText('SCHEMATIC · NOT GEOGRAPHIC',{exact:true})).toBeVisible()
  await expect(map).toContainText('cockpit berth')
  await expect(map).toContainText('cockpit vessel')

  const truth=page.getByRole('region',{name:'Operational truth ribbon'})
  await expect(truth).toContainText('SOURCE CONFLICTS')
  await expect(truth).toContainText('LATEST RECORD')
  await expect(truth).toContainText('UNMAPPED BERTHS')
})
