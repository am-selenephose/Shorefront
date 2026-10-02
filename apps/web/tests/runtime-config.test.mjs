import { execFileSync } from 'node:child_process'
import { existsSync, rmdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'
import assert from 'node:assert/strict'
import { test } from 'node:test'

test('browser test API cannot inherit a database or live-feed configuration', () => {
  const source = `import config from './playwright.config.ts';
    const env = {...process.env, ...config.webServer[0].env};
    const keys = ['DATABASE_URL', 'SHOREFRONT_DATA_DIR', 'SHOREFRONT_SCHEMA_MODE',
      'SHOREFRONT_PUBLIC_MODE', 'SHOREFRONT_STATIC_DIR', 'SHOREFRONT_WEATHER_URL',
      'SHOREFRONT_BERTH_PLAN_URL', 'SHOREFRONT_AIS_URL'];
    console.log(JSON.stringify(Object.fromEntries(keys.map(k => [k, env[k]]))));`
  const settings = JSON.parse(execFileSync(process.execPath,
    ['--experimental-strip-types', '--input-type=module', '-e', source], {
      cwd: new URL('..', import.meta.url), encoding: 'utf8',
      env: {...process.env, DATABASE_URL: 'postgresql://never-connect.invalid/live',
        SHOREFRONT_WEATHER_URL: 'https://never-connect.invalid/weather',
        SHOREFRONT_BERTH_PLAN_URL: 'https://never-connect.invalid/berths',
        SHOREFRONT_STATIC_DIR: '/never-use-this', SHOREFRONT_SCHEMA_MODE: 'verify',
        SHOREFRONT_PUBLIC_MODE: '1'},
    }))
  assert.equal(settings.DATABASE_URL, `sqlite:///${join(settings.SHOREFRONT_DATA_DIR, 'test.db')}`)
  assert.equal(dirname(settings.SHOREFRONT_DATA_DIR), tmpdir())
  assert.ok(settings.SHOREFRONT_DATA_DIR.split('/').at(-1).startsWith('shorefront-e2e-'))
  assert.equal(settings.SHOREFRONT_SCHEMA_MODE, 'migrate')
  assert.equal(settings.SHOREFRONT_PUBLIC_MODE, '0')
  assert.equal(settings.SHOREFRONT_STATIC_DIR, '')
  assert.equal(settings.SHOREFRONT_WEATHER_URL, '')
  assert.equal(settings.SHOREFRONT_BERTH_PLAN_URL, '')
  assert.equal(settings.SHOREFRONT_AIS_URL, 'http://127.0.0.1:9/e2e-unavailable')
  assert.ok(existsSync(settings.SHOREFRONT_DATA_DIR))
  // Only this probe's empty directory; actual browser runs own separate directories.
  rmdirSync(settings.SHOREFRONT_DATA_DIR)
})
