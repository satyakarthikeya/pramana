---
name: pramana-ui
description: Design rules, tokens and component specs for every PRAMANA screen (landing/upload, processing, results with PASS/REJECT and charts, proof drawer, memory/history). Load before writing or changing any frontend code. Calm-based, no AI-slop.
---

# PRAMANA UI skill

Base style: TypeUI **Calm** (warm greige surfaces with alternating tones, dark hero and footer, deep teal accent, pill controls, 24px bordered shadowless cards). Exact values below were derived from measured reference products (`references/ui-research.md`), because Calm's own spec is not public. Treat these tokens as the source of truth.

## Product rules the UI must never break
1. The verdict is **PASS or REJECT from the gate only** (q < alpha plus the effect band). The evidence score is for ordering and never shown as a verdict or a "confidence".
2. **Rejections are first-class**: always visible with their reason. No screen shows only successes. "No claim survived" is a result, not an error.
3. Every number shown comes from a proof object or from code run on the user's data. Charts only draw real data; nothing in the UI is invented, estimated or faked (no fake progress percentages).
4. Say "associated with", never "causes". Show n beside every statistic.
5. Fail closed in the wording: "Nothing was marked verified."

## Screens
1. **Landing**: dark hero, left-aligned. Product name PRAMANA, one plain sentence of the real promise, the upload dropzone overlapping the hero edge, and a real sample result (one verified and one rejected card) on the right. Below: how it decides (4 steps with real thresholds, mono), what a rejection looks like, dark footer.
2. **Processing**: vertical stage tracker (Profile data, Propose claims, Run tests, Verify and record). Four stages, because the API reports one progress line and the multiple-testing correction runs inside the last stage. The active stage is read from that line, never faked. A live mono line of real work ("Checking claim 2 of 3"). The detected columns appear beside it once the table is cleaned.
3. **Results**: verified claims as full cards ordered by effect size; rejected claims as compact rows with reasons; charts of the data; proof drawer on click.
4. **Memory / history**: table of runs and of stored PASS lessons, each linking back to its run.

## Tokens (light)
Surfaces: canvas `#F3EFE8`, alt band `#EAE4DA`, surface/card `#FBF9F5`, sunken `#F3EFE8`, hero `#14201F`, footer `#0F1817`.
Borders: `#D9D1C4` (cards), `#E4DDD1` (rows, gridlines), `#BFB5A5` (dropzone, hover, baselines).
Text on light: `#1F1C17`, `#4A443A`, `#6B6458` (not on `#EAE4DA` below 14px; use `#4A443A` there). On dark: `#EDEAE2`, `#C9C4B8`, `#9A9488` (16px+ only).
Accent teal `#0F5C58`; hover `#0B4744`; press `#083937`; tint `#D6E8E4`; on-dark `#5FC4B5`.
Status: PASS `#0F5C58`; REJECT `#B3411B`, tint `#F6E3DB`, ink `#8E2F0F`; NOT_TESTABLE/pending `#6B6458`.
Type: UI sans Inter Variable, claim and headline serif Source Serif 4, mono Geist Mono / JetBrains Mono (self-host in Docker, no CDN at runtime).
Scale (size/line, weight, tracking): display 56/60 w500 -0.022em; h1 40/44; h2 28/36; h3 22/28; lead 18/28; claim 20/30 serif w500; body 16/24; ui 14/20 w500; small 13/20; mono-label 11/16 caps +0.08em; code 13/20. Weights 400 body, 500 UI and headings, 600 only badges and wordmark. Max 7 sizes per page.
Spacing (4px base): 4 8 12 16 24 32 48 64 96 128. Card padding 24 (compact 16); gutter 24 (16 mobile); sections 96 (64 mobile). Widths: page 1120, results list 720 plus drawer 520.
Radii: 8 inputs/code, 12 nested panels, 24 cards/dropzone, 999 buttons/chips/badges. No others.
Heights: 28 chip/badge, 36 compact, 44 standard control and hit area, 52 hero CTA.

## Components
- **Verdict badge** (28px, 999 radius, mono caps 12px w600): VERIFIED = solid teal, check glyph. REJECTED = 1.5px vermillion outline on tint, X-in-square glyph. NOT TESTABLE = dashed grey outline, dash glyph. Glyph + fill style + word, so it survives grayscale. aria-label states the rule ("q = 0.003 is below alpha 0.05; effect in the medium band").
- **Claim card**: 24px radius, 1px border, no shadow, no coloured left edge. Mono caps claim type left, badge right; claim sentence in serif; variable chips; three mono stats (q, effect with its band word, n); "Open proof". Rejected rows: 72px, sentence, reason, badge.
- **Evidence chips**: 28px pills in mono (`col: bmi`, `n=4,812`, `Welch`, `seed 1234`, `BH FDR`). Shown above the claim detail in the drawer; click scrolls to that section.
- **Proof drawer**: right, 520px, 1px left border, no scrim blur, 200ms ease-out. Order: claim and verdict, test (method, null, n, seed, alpha), numbers (raw p, q, effect, band), chart, executed code with copy, data used, raw proof JSON collapsed. Esc closes and returns focus.
- **Chart container**: 24px card, purpose chip (DISTRIBUTION, GROUP COMPARISON, SCATTER + FIT), a one-sentence takeaway, direct labels, raw points at 0.45 opacity under summary marks, n footnote, "Table view" toggle, role=img with a summary label. Rejected claims' charts use neutral greys only.
- **Dropzone**: 24px, dashed 1.5px, left-aligned; states: idle, drag-over (solid teal on tint), chosen (name, size, rows x columns in mono, "Run verification"), error (vermillion with cause and fix), uploading (disabled).
- **Stage glyphs**: pending hollow, running rotating arc (static half-fill under reduced motion), done check, failed square with X, skipped dash.
- **Table**: no zebra; 40px mono caps header; 48px rows; numbers right-aligned mono tabular; selected row 2px teal inset on first cell.
- **Empty / error**: left-aligned heading, one sentence, one action; no illustration.

## Chart palette (colour-blind safe)
Categorical: `#0F5C58`, `#C47A1E`, `#3F6FB5`, `#A64D79`, `#6B6458`, `#7FB8AE` (max 5 series; add marker shape or dash too). Two-group comparisons use teal and amber. Sequential `#E3EFEC #B5D6CF #7FB8AE #3F8C84 #0F5C58`. Diverging `#B3411B #E3A58E #F3EFE8 #7FB8AE #0F5C58`. Chrome: gridlines `#E4DDD1`, axis `#BFB5A5`, text `#6B6458` 12px mono. No 3D, dual axes, rainbow, or pies over 3 slices.

## Anti-slop checklist (run before calling any screen done)
1. No gradients except one flat radial in the dark hero (6% lightness change at most).
2. No purple, indigo or violet (HSL hue 250 to 300). No default Tailwind blues (`#2563eb`, `#3b82f6`).
3. No `backdrop-filter`, no translucent cards, no `box-shadow` (focus rings are `outline`).
4. No emoji. One line-icon set, 16/20px, 1.5px stroke. No sparkle or wand icons.
5. No hype copy: "AI-powered", "magic", "unlock", "supercharge", "seamless", "insights". Every label names a real thing (a count, a column, a test).
6. No decorative blobs, orbs or mesh backgrounds. Every graphic is data or a control.
7. Left-aligned heroes showing real output. At most two centred elements per page. No row of three equal feature cards.
8. Results screen is not a uniform grid: verified cards, rejected rows and charts differ.
9. Radii, spacing and sizes only from the scales above. At most 4 text colours.
10. Verdicts never rely on colour alone (check in grayscale and with a deuteranopia filter).
11. Contrast at least 4.5:1 for text, 3:1 for large text and UI borders.
12. Numbers: mono, tabular, right-aligned, with units and n. No "significant!" language.
13. Loading shows real stages and counts. No fake percentages or spinner-only screens.
14. Motion: 120 to 200ms ease-out state changes plus one rotating running indicator; respect `prefers-reduced-motion`; nothing loops or fires on scroll.
15. Focus ring on every control, hit area at least 36px (44px for primary).
16. Charts have n, axis labels and a table view.

## Build notes
- Stack: Vite + React + TypeScript; charts with a small SVG/D3-based library; fonts self-hosted; built in a Docker multi-stage build and served by nginx behind the API. Nothing is fetched from a CDN at runtime.
- Keep tokens in one CSS file as custom properties; components read only tokens.
- Verify by screenshots at 1366px and 390px, keyboard-only pass, grayscale pass, and the checklist above, in Docker.
