import {expect,test} from '@playwright/test'

test('NOAA station context remains explicit and disabled without outbound opt-in',async ({page})=>{
  const runtime=await (await page.request.get('/api/v1/runtime/capabilities')).json()
  await page.goto(runtime.needs_setup?'/#setup=test-only-bootstrap-for-local-product-browser-suite':'/')
  if(runtime.needs_setup)await page.getByLabel('Full name').fill('Port Owner')
  await page.getByLabel('Email',{exact:true}).fill('owner@example.test')
  await page.getByLabel('Password',{exact:true}).fill('test-only customer passphrase 42')
  await page.getByRole('button',{name:runtime.needs_setup?'Create workspace':'Sign in',exact:true}).click()
  await expect(page.getByRole('link',{name:'Plan',exact:true})).toBeVisible()
  const response=await page.request.get('/api/v1/auth/me')
  const csrf=(await response.json()).csrf_token
  const send=await page.request.post('/api/v1/records/port',{
    headers:{Origin:new URL(page.url()).origin,'X-CSRF-Token':csrf,'Idempotency-Key':'noaa-port-e2e'},
    data:{record_id:'port-noaa-test',expected_revision:0,source:'Operator station selection',
          payload:{name:'US NOAA test port',timezone:'UTC',noaa_station_id:'9414290'}},
  })
  expect(send.status(),await send.text()).toBe(201)
  await page.goto('/#plan')
  // Out-of-band API writes are adopted through the operator's explicit refresh.
  await page.getByRole('button',{name:'Refresh records'}).click()
  const context=page.getByRole('region',{name:'External NOAA water level context'})
  await expect(context).toBeVisible()
  await expect(context).toContainText('9414290')
  await expect(context).toContainText('DISABLED')
  await expect(context).toContainText('No usable water-level observation is available')
  await expect(context).toContainText('PHYSICAL EXECUTION LOCKED')
  expect(await context.getByText(/ m$/, {exact:false}).count()).toBe(0)
  const updated=await page.request.post('/api/v1/records/port',{
    headers:{Origin:new URL(page.url()).origin,'X-CSRF-Token':csrf,'Idempotency-Key':'noaa-port-station-revision'},
    data:{record_id:'port-noaa-test',expected_revision:1,source:'Operator revised station selection',
      payload:{name:'US NOAA test port',timezone:'UTC',noaa_station_id:'9414750'}},
  })
  expect(updated.status(),await updated.text()).toBe(201)
  await page.getByRole('button',{name:'Refresh records'}).click()
  await expect(context.locator('.noaa-observation-top')).toContainText('Station 9414750')
})
