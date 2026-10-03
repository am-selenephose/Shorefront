// Run before the body/module renders so a saved night theme never flashes cream.
// Cream is the product default; an OS preference must not override that choice.
(() => {
  let theme = 'light'
  try {
    if (localStorage.getItem('shorefront.theme') === 'dark') theme = 'dark'
  } catch {
    // Storage can be unavailable in private/embedded contexts. Keep the default.
  }
  document.documentElement.dataset.theme = theme
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.content = getComputedStyle(document.documentElement).getPropertyValue('--background').trim()
})()
