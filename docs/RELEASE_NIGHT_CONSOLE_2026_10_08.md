# Night Console v4 release, 2026-10-08

- Application commit: 038a6885f6b80fc057cb19ac3f81c25c6867a2df
- Deployment: https://shorefront.animantum.com
- Web image: shorefront-web:operational-038a688
- Unchanged API image: shorefront-api:operational-66a1393
- Runtime mode: operational; production_ready flag remains false.
- New interactive command shortcut: Control+K/Meta+K enters real customer-record search, Escape clears and dismisses.
- Release source includes detailed competitive pattern study in NIGHT_CONSOLE_UI_BENCHMARK_2026_10_08.md.

## Verified

- Before change, test rendered active night berth switch as cream (RGB 236,234,193) rather than warm peach.
- After change, computed selected berth controls and active navigation both RGB(254,175,119).
- Animated glow avoided: focused call box shadow uses fixed 2px peach ring plus 22px ambient shadow.
- Night mode added layered dark teal/peach surface and schematic/geo overlay treatments, readiness/what-if focus, coordinated hero, call-register and action states.
- Chromium full operational browser test suite: 33 passed.
- Isolated authenticated Readiness/What-if browser test suite: 2 passed (including 390px night view and shortcut).
- Training-mode browser suite: 31 passed using tested production assets. Initial dev-server test path had permission failure in an unrelated temporary Vite cache, resolved by using the built asset preview, without changing the production source config.
- Frontend TypeScript/Vite release build: passed.
- Web built-image HTTP/TLS cache and header regressions: 2 passed.
- Public, live browser recheck after cutover: HTTPS 200, dark peach controls RGB(254,175,119), selected-call ambient ring present, 390px mobile no horizontal overflow.
- Public /readyz and /api/v1/runtime/capabilities: 200. Public unauthenticated /api/v1/readiness: 401.
- Web and API containers healthy; Compose cutover used --no-deps web.
- Live root HTML digest matches served nginx HTML: sha256 59a654bcec093699a2332b62bc90a490a050a76d0a2ddc13ed6a689fb024f869.
- Physical PostgreSQL container ID unchanged: f8faa1582de507aad6344bc7f00222b3a229230e0e07acab952474a3609bb04d.
- Post-cutover live database record/decision/audit counts: 0/0/1 (same as before).
- Rollback web image alias retained: shorefront-web:rollback-pre-038a688.

## Boundaries

- Design parity and restored brand identity are proven for exercised routes/viewports.
- No claim of independent measured superiority against a competitor or of a 1000x improvement.
- No new AIS, weather, terminal equipment, JIT, 3D digital twin or crane/gang planning integration.
- No business data was inserted into the live operational installation.
- The browser public showcase is intentionally fictional; isolated authenticated integration tests use disposable data.
- The application keeps its advisory/production_ready=false contract, with enterprise readiness still pending security, contracted feeds and operator validation.
- Existing MapLibre large-bundle build warning remains open as a performance optimization task.
