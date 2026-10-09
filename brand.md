# Shorefront brand — cream-first coastal workspace with night mode

Owner-selected on 2026-10-02 from `cvetovaya-palitra-1662.png`.
This replaces the unapproved Tidal Jade proposal. The coastal palette belongs
to Shorefront. No logo or naming clearance is implied.

**Owner correction:** pale cream is the base, not the text colour on a dark
workspace. The earlier dark-first default was rejected. Current direction:
light, technical and geometric, with Space Grotesk replacing Inter. The owner
subsequently requested the original inverse contrast as an optional dark mode;
it does not replace the cream default or revert the new typography and layout.

## Exact reference colours

The supplied 400 × 400 image was sampled at y=310, at x=35, 118, 200, 280 and
362, inside the five flat swatches and away from the photograph and watermark.

| Colour | Exact sRGB | Role |
|---|---|---|
| Deep blue-green | `#192F32` | Main text, selected navigation, focus rings and map outlines |
| Muted teal | `#64989A` | Structural accents and preferred-plan marker |
| Pale cream | `#ECEAC1` | Exact main canvas and sidebar base, reversed text on ink |
| Warm yellow | `#FED987` | Warning fills, occupied-berth badge and map berth markers |
| Peach | `#FEAF77` | Actions, exposure panel, brand tile and map vessel markers |

## Implementation

`apps/web/src/styles.css` is the single colour authority. Its `:root` contains
the five exact seeds, then semantic surfaces, text, borders and status tokens.
Keep exact sRGB values for source fidelity and MapLibre canvas compatibility.
`HarborMap.tsx` reads the map roles from computed CSS; do not duplicate hex values
inside components. Browser theme-colour metadata follows the active canvas token.

The header has a keyboard-accessible **Dark mode ON/OFF** toggle. Cream is the
default even if the device prefers dark mode. An explicit choice is stored in
`localStorage['shorefront.theme']` and restored before the application renders.
Invalid/blocked storage falls back to cream; the toggle still works in memory
when persistence is unavailable. No account or server preference is written.

The existing operational flows remain. Their presentation now has a geometric
type scale, open metric group, full-height exposure summary, larger timeline
lanes, lighter map treatment and accessible horizontal navigation on smaller
screens. This is not completion of the wider commercial product programme.

### Derived functional colours

- Panel: `#F7F5E3`; inset: `#EFEDD0`; hover/preferred surface: `#DCE6D4`.
- Secondary text: `#415B57`; the exact mid-teal is not body text on cream.
- Decorative divider: `#B2BAA1`; strong control border: `#4E7675`.
- Success: `#315D40` on `#E0EAD3`; warning: `#704710` on exact yellow.
- Danger: `#973C34` on `#F7DFD3`; contingency: `#794322` on `#FBE1C5`.
- Separate success/danger hues preserve operational meaning. Existing labels
  remain visible; never communicate status by colour alone.

### Night-mode roles

- Canvas: exact deep blue-green `#192F32`; main text: exact cream `#ECEAC1`.
- Panel: `#203B3D`; inset: `#192F32`; hover/selected: `#29494A`.
- Secondary text: `#A6C5C3`; strong borders: exact teal `#64989A`.
- Peach remains the action/exposure fill with **dark ink text**, not cream text.
- Warning: exact yellow on `#443B26`; danger: `#FFAB9F` on `#492F2D`;
  success: `#B9DBB1` on `#263E35`.
- Keyboard focus rings use peach; selected navigation keeps a peach edge.
- The existing map is repainted with subdued raster tiles and cream vessel
  labels with dark halos. Do not remount the map or reset its viewport on toggle.
- Colour tokens are shared by loading, operational, recovery and adapter states.
  The bootstrap script is placed after the head stylesheet, before visible body
  content; this ordering also works with Vite's production CSS hoisting.

### Key contrast pairs

Ratios use WCAG sRGB relative luminance, not perceptual lightness estimates.

| Foreground / background | Ratio |
|---|---:|
| Deep blue-green / cream | 11.45:1 |
| Deep blue-green / peach button | 7.77:1 |

Browser tests also check computed text/background pairs across real rendered
operational components. These checks are not an exhaustive accessibility audit.

## Typography and composition

**Space Grotesk** for headings, navigation, body, controls and large tabular metrics.
**Space Mono** for timestamps and short technical labels, not paragraphs.
Both are bundled as local WOFF2 fonts with their SIL OFL copyright notices;
see `apps/web/public/fonts/README.md` for upstream URLs and SHA-256 checksums.
Latin coverage is bundled; other scripts fall back to system fonts. No runtime
Google Fonts request is needed. Font preload and `font-display: swap` are used.

Type hierarchy: 28–40px page heading, 36px metrics, 17–18px section/card headings,
12–14px operational body, 9–11px short technical annotations. Controls have at
least 40px height. The futuristic character comes from geometry, precise lines,
tabular data and restrained accents; do not introduce neon effects or dense tiny
monospaced body text. The chamfered S tile is a provisional product mark.
The supplied photograph is a colour reference, not an asset licensed for shipping.

Use peach for actions and the exposure summary. Keep yellow for attention and berth
identification. Teal creates structure; cream is the canvas. Use semantic
tokens rather than local component colours. Do not borrow another product's identity.

See [theme-switch verification](docs/THEME_SWITCH_VERIFICATION.md) for the current
browser checks, both-mode screenshots and exact verification limits.

## Voice

Direct, factual and calm. Distinguish simulated data, human approval, advisory
coordination and physical execution. Avoid unsupported production-readiness or
autonomy claims.

Dark-first implementation backup: `/tmp/shorefront-cream-backup.zGJgP7/` (temporary).
Earlier pre-palette backup: `/tmp/shorefront-palette-backup.45HWWe/` (temporary).
Durable source baseline: commit `f83dec1` before the palette change.
