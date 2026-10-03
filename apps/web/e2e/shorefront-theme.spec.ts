import { expect, test, type Page } from '@playwright/test'
import { writeFile } from 'node:fs/promises'

async function mapBrightness(page: Page, screenshot: Buffer) {
  // Inspect real rendered canvas pixels without a test-only map API or private
  // React/MapLibre state. Screenshot decoding stays entirely in the browser.
  return page.evaluate(async base64 => {
    const image = new Image()
    image.src = `data:image/png;base64,${base64}`
    await image.decode()
    const canvas = document.createElement('canvas')
    canvas.width = image.width
    canvas.height = image.height
    const context = canvas.getContext('2d')!
    context.drawImage(image, 0, 0)
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
    let sum = 0
    for (let i = 0; i < pixels.length; i += 4) sum += .2126 * pixels[i] + .7152 * pixels[i + 1] + .0722 * pixels[i + 2]
    return sum / (pixels.length / 4)
  }, screenshot.toString('base64'))
}

async function textContrast(page: Page) {
  return page.evaluate(() => {
    const rgb = (value: string) => (value.match(/[\d.]+/g) || []).map(Number)
    const luminance = (value: number[]) => value.slice(0, 3).reduce((sum, n, i) => {
      const channel = n / 255
      return sum + (channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4) * [.2126, .7152, .0722][i]
    }, 0)
    const selectors = ['.eyebrow', '.brand span', '.side-foot small', 'nav a', '.metric-card span', '.metric-card strong', '.panel-title small', '.berth-row div span', '.berth-state', '.risk', '.gantt-call span', '.gantt-call small', '.gantt-tick span', '.scenario-grid button span', '.service-dag-node b', '.service-dag-node em', '.resource-status', '.resource-calendar', '.recovery-rationale p', '.recovery-metrics span', '.operator-session-copy small', '.source-card small', '.adapter-row small', '.shorefront-context-strip span', '.system-state', '.mode-buttons button', '.theme-toggle', 'footer']
    return selectors.flatMap(selector => Array.from(document.querySelectorAll<HTMLElement>(selector)).filter(element => element.getClientRects().length > 0).map(element => {
      let ancestor: HTMLElement | null = element
      let bg = getComputedStyle(document.body).backgroundColor
      while (ancestor) {
        const candidate = getComputedStyle(ancestor).backgroundColor
        if (rgb(candidate).length === 3 || rgb(candidate)[3] === 1) { bg = candidate; break }
        ancestor = ancestor.parentElement
      }
      const fg = getComputedStyle(element).color
      const a = luminance(rgb(fg)), b = luminance(rgb(bg))
      return { selector, foreground: fg, background: bg, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) }
    }))
  })
}

test('day and night modes reverse contrast, persist and preserve the operational view', async ({ page }, testInfo) => {
  await page.request.post('/api/v1/demo/reset')
  // The owner chose cream as the default, even on a dark-system device.
  await page.emulateMedia({ colorScheme: 'dark' })
  const workerReady = page.waitForEvent('worker')
  await page.goto('/#control-tower')
  const worker = await workerReady
  const workerResponse = await page.request.get(worker.url())
  // A production SPA can return index.html with status 200 for a missing worker.
  expect(workerResponse.headers()['content-type']).toMatch(/javascript/)
  const toggle = page.getByRole('button', { name: 'Dark mode', exact: true })
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(236, 234, 193)')
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  const canvas = await page.locator('.maplibregl-canvas').elementHandle()
  await page.getByRole('button', { name: /B07 Berth Crunch/i }).click()
  await expect(page.locator('.recovery-card').first()).toBeVisible()
  await page.waitForLoadState('networkidle')
  const map = page.locator('.maplibregl-canvas')
  const lightMap = await map.screenshot({ path: testInfo.outputPath('live-map-light.png') })
  const lightBrightness = await mapBrightness(page, lightMap)
  const requestMethods: string[] = []
  page.on('request', request => {
    if (request.url().includes('/api/')) requestMethods.push(request.method())
  })
  const contrastByMode = []
  contrastByMode.push({ mode: 'light', pairs: await textContrast(page) })
  await toggle.focus()
  await page.keyboard.press('Space')
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
  await expect(toggle).toBeFocused()
  await expect(toggle).toHaveCSS('outline-color', 'rgb(254, 175, 119)')
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(25, 47, 50)')
  await expect(page.locator('body')).toHaveCSS('color', 'rgb(236, 234, 193)')
  await expect(page.locator('.metric-card:last-child strong')).toHaveCSS('color', 'rgb(25, 47, 50)')
  await expect(page.locator('h1')).toHaveCSS('font-family', /Space Grotesk/)
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#192f32')
  expect(await canvas!.evaluate(element => element === document.querySelector('.maplibregl-canvas'))).toBe(true)
  expect(requestMethods.filter(method => method !== 'GET')).toEqual([])
  await expect(page.locator('.recovery-card').first()).toBeVisible()
  // Prove that the existing canvas repaints now, not only after a saved-theme
  // reload. The broad ratio tolerates different real basemap tiles and labels.
  await expect.poll(async () => mapBrightness(page, await map.screenshot())).toBeLessThan(lightBrightness * .65)
  await map.screenshot({ path: testInfo.outputPath('live-map-dark.png') })
  contrastByMode.push({ mode: 'dark', pairs: await textContrast(page) })
  for (const sample of contrastByMode) {
    expect(sample.pairs.length).toBeGreaterThan(100)
    expect(sample.pairs.filter(pair => pair.ratio < 4.5), sample.mode).toEqual([])
  }
  const contrastPath = testInfo.outputPath('theme-text-contrast.json')
  await writeFile(contrastPath, JSON.stringify(contrastByMode, null, 2))
  await testInfo.attach('theme-text-contrast', { path: contrastPath, contentType: 'application/json' })
  expect(await page.evaluate(() => localStorage.getItem('shorefront.theme'))).toBe('dark')
  await page.reload()
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(25, 47, 50)')
  for (const [name, width, height] of [['desktop', 1440, 1000], ['tablet', 768, 1024], ['mobile', 375, 812]] as const) {
    await page.setViewportSize({ width, height })
    await page.evaluate(() => window.scrollTo(0, 0))
    await expect(toggle).toBeInViewport()
    expect((await toggle.boundingBox())!.height).toBeGreaterThanOrEqual(40)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: testInfo.outputPath(`dark-${name}.png`) })
    await page.screenshot({ path: testInfo.outputPath(`dark-${name}-full.png`), fullPage: true })
  }
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(236, 234, 193)')
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#eceac1')
  expect(await page.evaluate(() => localStorage.getItem('shorefront.theme'))).toBe('light')
  await page.reload()
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
})

test('held keyboard and pointer controls keep readable secondary text in dark mode', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('shorefront.theme', 'dark'))
  await page.goto('/#control-tower')
  const toggle = page.getByRole('button', { name: 'Dark mode', exact: true })
  const scenario = page.getByRole('button', { name: /B07 Berth Crunch/i })
  for (const [button, secondary] of [[toggle, toggle.locator('.theme-toggle-state')], [scenario, scenario.locator('span')]] as const) {
    await button.focus()
    await page.keyboard.down('Space')
    await expect.soft(button).toHaveCSS('background-color', 'rgb(254, 217, 135)')
    await expect.soft(secondary).toHaveCSS('color', 'rgb(25, 47, 50)')
    // Move focus before release to inspect the pressed state without activation.
    await button.evaluate(element => element.blur())
    await page.keyboard.up('Space')
    await button.hover()
    await page.mouse.down()
    await expect.soft(button).toHaveCSS('background-color', 'rgb(254, 217, 135)')
    await expect.soft(button).toHaveCSS('color', 'rgb(25, 47, 50)')
    await expect.soft(secondary).toHaveCSS('color', 'rgb(25, 47, 50)')
    await page.mouse.move(0, 0)
    await page.mouse.up()
  }
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
})

test('saved dark mode is applied before the application module loads', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('shorefront.theme', 'dark'))
  await page.route('**/src/main.tsx', route => route.abort())
  await page.route('**/assets/*.js', route => route.abort())
  await page.goto('/#control-tower')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(25, 47, 50)')
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#192f32')
  await expect(page.locator('#root')).toBeEmpty()
})

test('invalid preferences and blocked storage do not prevent switching themes', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('shorefront.theme', 'invalid-theme'))
  await page.goto('/#control-tower')
  const toggle = page.getByRole('button', { name: 'Dark mode', exact: true })
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Storage unavailable', 'SecurityError') } })
  })
  await page.reload()
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(25, 47, 50)')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
})
