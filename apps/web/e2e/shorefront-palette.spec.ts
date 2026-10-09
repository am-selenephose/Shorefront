import { expect, test } from '@playwright/test'
import { writeFile } from 'node:fs/promises'

test('selected coastal palette reaches the rendered shell and readable operational labels', async ({ page }, testInfo) => {
  await page.request.post('/api/v1/demo/reset')
  await page.goto('/#control-tower')
  await expect(page.locator('.shell')).toBeVisible()
  // Consumer-visible requirements from the supplied swatches, not source-string checks.
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(236, 234, 193)')
  await expect(page.locator('body')).toHaveCSS('color', 'rgb(25, 47, 50)')
  await expect(page.locator('.brandmark')).toHaveCSS('background-color', 'rgb(254, 175, 119)')
  await expect(page.locator('.brandmark')).toHaveCSS('color', 'rgb(25, 47, 50)')
  await expect(page.locator('.berth-state.occupied').first()).toHaveCSS('background-color', 'rgb(254, 217, 135)')

  await page.getByRole('button', { name: /B07 Berth Crunch/i }).click()
  await expect(page.locator('.recovery-card').first()).toBeVisible()
  const contrast = await page.evaluate(() => {
    const rgb = (value: string) => (value.match(/[\d.]+/g) || []).map(Number)
    const luminance = (value: number[]) => value.slice(0, 3).reduce((sum, n, i) => {
      const channel = n / 255
      return sum + (channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4) * [.2126, .7152, .0722][i]
    }, 0)
    const selectors = ['.eyebrow', '.brand span', '.side-foot small', 'nav a', '.metric-card span', '.panel-title small', '.berth-row div span', '.gantt-tick span', '.scenario-grid button span', '.service-dag-node em', '.resource-calendar', '.recovery-rationale p', '.recovery-metrics span', '.operator-session-copy small', '.source-card small', '.adapter-row small', '.shorefront-context-strip span', 'footer']
    return selectors.flatMap(selector => Array.from(document.querySelectorAll<HTMLElement>(selector)).map(element => {
      let ancestor: HTMLElement | null = element
      let bg = 'rgb(236, 234, 193)'
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
  expect(contrast.length).toBeGreaterThan(30)
  expect(contrast.filter(pair => pair.ratio < 4.5)).toEqual([])
  const contrastPath = testInfo.outputPath('operational-text-contrast.json')
  await writeFile(contrastPath, JSON.stringify(contrast, null, 2))
  await testInfo.attach('operational-text-contrast', { path: contrastPath, contentType: 'application/json' })

  const token = page.getByLabel('Operator access token')
  await token.fill('test-only-focus-check')
  await page.keyboard.press('Tab')
  const verify = page.getByRole('button', { name: 'Verify' })
  await expect(verify).toBeFocused()
  await expect(verify).toHaveCSS('outline-style', 'solid')
  await expect(verify).toHaveCSS('outline-color', 'rgb(25, 47, 50)')
  for (const [name, width, height] of [['desktop', 1440, 1000], ['tablet', 768, 1024], ['mobile', 375, 812]] as const) {
    await page.setViewportSize({ width, height })
    await page.evaluate(() => window.scrollTo(0, 0))
    // External map tiles are not part of app readiness; wait for pending assets
    // here specifically so visual evidence is not an intermediate tile mosaic.
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: testInfo.outputPath(`cream-${name}.png`), fullPage: false })
    await page.screenshot({ path: testInfo.outputPath(`cream-${name}-full.png`), fullPage: true })
  }
})

test('loading identity uses the same coastal palette without the retired monogram', async ({ page }) => {
  await page.route('**/api/v1/harbor', route => route.abort())
  await page.routeWebSocket('**/ws/harbor', () => {})
  await page.goto('/#control-tower')
  const boot = page.locator('.boot')
  await expect(boot).toBeVisible()
  expect(await boot.evaluate(element => getComputedStyle(element, '::before').content)).toBe('"S"')
  await expect(boot).toHaveCSS('color', 'rgb(25, 47, 50)')
})

test('palette preserves disabled actions, reduced motion and distinct critical timeline risk', async ({ page }) => {
  await page.request.post('/api/v1/demo/reset')
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/#control-tower')
  await page.getByRole('button', { name: /B07 Berth Crunch/i }).click()
  const disabledAction = page.getByRole('button', { name: 'Authenticate to apply' }).first()
  await expect(disabledAction).toBeDisabled()
  await disabledAction.hover()
  await expect.soft(disabledAction).toHaveCSS('background-color', 'rgb(254, 175, 119)')
  await expect.soft(disabledAction).toHaveCSS('color', 'rgb(25, 47, 50)')
  const recalculate = page.getByRole('button', { name: 'Recalculate' })
  await expect(recalculate).toBeEnabled()
  await expect.soft(recalculate).toHaveCSS('transition-duration', '0s')
  await expect(page.locator('.gantt-call.high').first()).toBeAttached()
  await expect(page.locator('.gantt-call.critical').first()).toBeAttached()
  const riskBorders = await page.evaluate(() => ['high', 'critical'].map(risk =>
    getComputedStyle(document.querySelector(`.gantt-call.${risk}`)!).borderTopColor,
  ))
  expect.soft(riskBorders[0]).not.toBe(riskBorders[1])
})

test('cream workspace loads its own geometric fonts and keeps mobile controls usable', async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.abort())
  await page.route('https://fonts.gstatic.com/**', route => route.abort())
  await page.goto('/#control-tower')
  await expect(page.locator('.shell')).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
  await expect(page.locator('h1')).toHaveCSS('font-family', /Space Grotesk/)
  const fonts = await page.evaluate(() => [...document.fonts].filter(font => font.status === 'loaded').map(font => font.family.replaceAll('"', '')))
  expect(fonts).toContain('Space Grotesk')
  expect(fonts).toContain('Space Mono')
  await expect(page.locator('.metric-card strong').first()).toHaveCSS('font-size', '36px')

  for (const width of [1440, 1280, 768, 375]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    const sizes = await page.locator('.berth-row b, .scenario-grid button span, .source-card small').evaluateAll(elements => elements.map(element => parseFloat(getComputedStyle(element).fontSize)))
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(12)
  }
  const navigation = page.getByRole('navigation', { name: 'Shorefront workspace' })
  await expect(navigation).toBeVisible()
  await navigation.getByRole('link', { name: 'Recovery', exact: true }).click()
  await expect(page).toHaveURL(/#recovery$/)
  const controls = await page.locator('button, input, nav a').evaluateAll(elements => elements.filter(element => element.getClientRects().length > 0).map(element => element.getBoundingClientRect().height))
  expect(Math.min(...controls)).toBeGreaterThanOrEqual(40)
})
