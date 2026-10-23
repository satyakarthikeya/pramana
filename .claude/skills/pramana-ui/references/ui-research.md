# PRAMANA UI research (measured 2026-10-22, logged-out public pages, 1024x768 pane)

Method: computed styles read via JS on each landing page, plus screenshots. Nothing signed into, no forms submitted, no cookie banner accepted (Perplexity and Grid showed banners; left untouched). Measurements and structure only; no copy or assets recorded.
Caveats (honest limits):
- Perplexity's answer/citation view needs a submitted query, so it was NOT observed here. The citation notes in 1.1 are marked "prior knowledge, unverified".
- Hex and Observable pages use scroll-driven/animated layouts; some computed colours were mid-transition and are flagged "approx". Hex screenshot was mostly blank in this pane (scroll container), so Hex layout judgements are from computed values only.
- "Grid" = grid.is, "The spreadsheet engine for AI agents" (a spreadsheet product; the only data/spreadsheet product I could identify at that domain).
- Viewport was 1024 wide, so some sites served their tablet/small-desktop breakpoint.

---------------------------------------------------------------------
## (a) Per-site findings

### 1.1 Perplexity (perplexity.ai)
- Logged-out lands directly in the product shell: left sidebar (New, Computer, Automations, Artifacts, Customize, Projects, Recents "No projects / No recent questions", Sign in pinned at bottom). No marketing hero. The empty states are one plain sentence each.
- Font: custom "pplxSans", body 16/24, weight 360 (variable font used at non-standard weights: 360 body, 470 labels). Small UI labels 14/20 at weight 470.
- Body bg #000000, text #ffffff, secondary text #dadfe3, tertiary = white at 50-65% alpha.
- Ask box: bg #1a1e21, 640px wide, 117px tall, 1px border (transparent), placeholder 16/24. Controls inside are 24px (r=6px) and 32px (r=9999px) icon buttons.
- Mode cards under the box: 314x88, radius 11px, flat fill with NO shadow: #016a71 (teal, highlighted) and #081f22 (near-black teal). Title 14/20 w470, description 16/24 in the same card.
- Accent family is teal. Relevant to PRAMANA: a teal accent on a dark surface is shipped by a mainstream product and is not "AI purple".
- Cookie banner is a small bottom-right dialog with two buttons (Decline optional / Got it): non-blocking.
- Prior knowledge, unverified here: answers show a numbered source row first, inline numeric citation markers in prose, each source as a small card with favicon + domain. Idea to adopt: evidence is a first-class row ABOVE the answer, not a footnote.

### 1.2 Linear (linear.app)
- Font: Inter Variable, body 16/24 w400; custom weights 510 (medium) and 590 (semibold). Tight tracking everywhere.
- H1 56/61.6 w510, ls -1.232px (-0.022em). H2 40/44 w510 ls -0.88px. H3 20/26.6 w590 ls -0.24px. Body 15/24 ls -0.165px; small 14/21.
- Colours: bg #08090a, text-1 #f7f8f8, text-2 #d0d6e0, text-3 #8a8f98, border #23252a, raised surface #1c1c1f, brand #5e6ad2 (used very sparingly).
- Layout: --page-max-width 1024px, --page-padding-inline 24px, header 72px, section padding-top 128px, wide containers up to 1400px for product screenshots.
- Buttons: pill (r=9999px). Nav 32px high, 13px text, 12px side padding; primary CTA 44px high, 16px w510, 20px side padding, fill #e5e5e6 with #08090a text (a light button on dark, NOT the brand colour).
- Motion: hero headline/screenshots blur-and-fade in on load (screenshot caught the blurred state). Cue: slow, one-time entrance, no looping.
- Takeaway: the type scale is tiny in range (13/14/15/16/20/40/56) and quality comes from tracking, weight 510, and grey text steps, not from colour.

### 1.3 Vercel (vercel.com)
- Fonts: Geist Sans and Geist Mono (mono used for secondary paragraph text in the hero list).
- H1 64/64 w400 ls -3.84px (-0.06em). H2 56/56 w450 ls -3.36px. Large lead 24/32 w450 ls -0.96px, colour #a1a1a1. Body 16/24, #ededed on #000.
- Border colour #1f1f1f; secondary button fill #0a0a0a; primary fill #ededed on #0a0a0a text.
- Buttons: nav 32px high r=6px 14px w500; hero 40px high pill r=full 16px w500 12px padding.
- Max widths: 1448px outer, 992/1024px inner text blocks. 1105 DOM nodes on home (lean).
- Layout: headline LEFT-aligned in a left column, short three-line list in right column (not centred); logo strip in a single row; big whitespace. Very few colours: it is basically black, #ededed, #a1a1a1.
- Takeaway: heavy negative tracking at display sizes, mono for supporting detail, left-aligned asymmetry.

### 1.4 Hex (hex.tech)
- Light, warm-white canvas with a faint graph-paper grid; ink colour #14141c (near-black with a violet cast), body text #31263b / #43394c.
- Three type voices: PP Formula SemiExtended w700 (H1 64.4/77.2 ls -1.6px; H2 53.4/69.4), PP Formula w800 (H3 25.6/33.3), Cinetype grotesque body 14/22, Cinetype Mono 10/12 UPPERCASE labels with ls 0.83px ("TRUSTED BY...").
- Buttons: 50px high, 20px horizontal padding, radius 0 (square), ghost outline 1px #dbd7da, primary has a gradient fill (approx, warm cream-to-pink; not recommended).
- Radii present on page: 3px (57 elements, small tags), 4, 6, 8, 12px; 40px only for ~5 pills. Containers 1240px / 1000px.
- A tab strip at the top of the page uses small icons and emoji (it mimics an app tab bar). Lesson: Hex gets its identity from the grid paper and mono caps labels, not from decoration; do NOT copy the emoji.
- Takeaway: uppercase mono micro-labels (10-11px, +0.8px tracking) as a systematic metadata voice.

### 1.5 Observable (observablehq.com)
- Fonts: Inter Variable (UI, 14/20 w500), Source Serif 4 Variable (prose 17/25.5 = 1.5), Spline Sans Mono Variable (timestamps, code, 12/21).
- Hero: navy block (approx #12162b), headline in two weights/colours (lead line muted, key line white at very large size), then a serif paragraph with bold lead-in. Product shown as notebook "tab" cards with a small label chip on top-left edge ("Advanced data visualizations", "Ad hoc data analysis").
- Max widths: 1152px (11 uses), 1024px (6), 384px card columns (7). Radii: 4px (102 uses), 6px (63), full-pill (6), 20px (1). So the system is almost entirely 4-6px radii.
- Body text colour #1b1e23; link/ink variants have a slight magenta/indigo cast.
- Takeaway: serif body for explanatory text next to sans UI and mono data gives a "document" feel that suits claims plus proofs. Chart cards carry a labelled tab chip, so the chart's purpose is named, not just titled.

### 1.6 Julius AI (julius.ai)
- Logged-out lands on a prompt app ("What can I do for you today?") with a slim icon rail, announcement pill, prompt box, mode chips (r=9999, 28px, 12px w500), and a template grid of grey-gradient image tiles.
- Font: Inter 16/24 body #404040; H1 only 30/36 w500 ls -0.75px; nav 14/20 w600 ls -0.14px.
- Primary button #2563eb (default Tailwind blue-600), 36px high, r=6px, 14px w500. Prompt box 492x56, r=6-8px.
- Radii: 8px (18), 6px (11), 24px (1).
- Verdict: this is the generic "AI product" look (default Tailwind blue, centred stack, template tiles). Useful as a counter-example: centred-everything + default blue + a row of decorative tiles. Chart/proof presentation was not visible logged-out.

### 1.7 Grid (grid.is)
- Dark forest-green hero (radial lighter glow at top, about #1b4d3e to #164a3c) with mint accent #3ccda4 for the primary button (text #164a3c), 57px high, r=4px, 16px w600.
- Secondary: transparent, 1px white at 40% alpha, 59px high, r=4px. Tiny pills 24px high r=999 (white 12% fill, 40% border) for "Try it out / Build an AI assistant" tabs. COPY button 25px high, 11px mono, white 8% fill, 15% border.
- Fonts: custom grotesque "nbi" body 15/21 and "nbiMono"; H1 39.9/43.9 w400; H2 31.2/37.4; muted paragraphs white at 60%.
- Layout: left headline + CTAs, right column with labelled code panels ("HUMANS" / "AGENTS", mono 11px caps labels). Max widths 1160/1240px.
- Takeaway: a dark-green hero with ONE mint action is the closest existing analogue to the Calm dark hero + teal accent. Square-ish 4px buttons, mono caps column labels, install command as the proof of "real".

---------------------------------------------------------------------
## (b) Cross-site patterns that signal quality

1. Narrow type palette: 6-8 sizes total. Linear uses 13/14/15/16/20/40/56; Observable's UI is 12/14/16/17.
2. Display type carries negative tracking: Linear -0.022em, Vercel -0.06em. Body stays at 0 to -0.011em.
3. Non-integer weights (360, 450, 470, 510, 590) used to tune one variable font instead of changing family. Gives refinement cheaply.
4. Only 3-4 grey steps for text (e.g. #f7f8f8 / #d0d6e0 / #8a8f98 on dark; #ededed / #a1a1a1 on Vercel). Hierarchy by lightness, not by colour.
5. The accent is rare: Linear's brand colour is not on its main CTA; Vercel's and Linear's CTAs are neutral. Colour appears for status and one action.
6. Small radii dominate (4-6px; Observable 4/6, Hex 3-6, Grid 4); full pills are reserved for chips and nav CTAs. Cards are flat: no drop shadows measured on any site's primary cards.
7. Left-aligned asymmetric heroes (Vercel, Grid, Linear): headline left, supporting list or code right. Only Julius centres everything.
8. Monospace as a metadata voice (Hex 10px caps, Grid 11px caps labels, Observable timestamps, Vercel secondary list). Used for numbers, labels, commands.
9. Consistent control heights: 32px compact, 36-44px standard, 50-59px hero CTA. Never mixed ad hoc.
10. Container discipline: 1024-1240px content, 1448px for imagery, 24px gutters, ~128px section padding.
11. Border colour is a hairline 1px a few percent off the surface (#23252a on #08090a; #1f1f1f on #000).
12. Real product shown (notebook tab cards, code panels, app shell) rather than abstract illustration. Observable and Grid label the real thing.
13. Motion is one-time and short (Linear blur-in). No looping decorative animation was seen.
14. Empty states are one honest sentence (Perplexity: "No recent questions").
15. Blocking UI is avoided: cookie banner is a small corner card.

---------------------------------------------------------------------
## (c) Components to adopt, mapped to Calm

Calm base facts: warm greige surfaces with alternating tones, dark hero/footer, deep teal accent, pill controls, 24px bordered shadowless cards. Tokens referenced below are defined in section (e).

### Upload dropzone (landing)
- Container: 24px radius, 1.5px DASHED border `--border-strong` #BFB5A5 on `--surface` #FBF9F5, min-height 220px, padding 32px. Left-aligned content (not centred): H3 "Drop a CSV or XLSX" 22/28, one line of limits in `--text-3` 14/20 mono ("CSV, XLSX - up to 50 MB - first sheet only"), then a pill button "Choose file" (44px high, r=999, fill #0F5C58, text #FBF9F5).
- Right of the dropzone inside the same card: a column of 3 mono caps facts (10-11px, +0.8px tracking) like "WHAT HAPPENS / 1 PROFILE / 2 PROPOSE / 3 TEST / 4 VERIFY" (Hex/Grid mono label voice).
- States: hover/drag-over = border becomes SOLID 2px #0F5C58, bg `--accent-tint` #D6E8E4; focus-visible = 2px outline #0F5C58 offset 3px; file chosen = filename + size + row/column count in mono, "Replace" ghost pill, primary becomes "Run verification"; error = 1.5px solid #B3411B border, message with the reason and the fix ("12 columns have no header. Add a header row and retry."); disabled while uploading.
- Hero (dark #14201F) sits above with name PRAMANA and one plain sentence of what it does; dropzone overlaps the hero/greige boundary by 48px (Calm alternating tones).

### Stage tracker (processing view)
- Vertical list, 5 stages: Profile data, Propose claims, Run tests, Correct for multiple testing, Verify and write proof. (Match actual pipeline: gate is q < alpha plus effect band; not scored.)
- Row: 56px min height, 24px dot/glyph column, stage name 16/24 w500, right-aligned mono status/elapsed ("00:04").
- Glyphs (shape differs per state, not just colour): pending = hollow circle 12px #BFB5A5; running = 12px circle with 2px teal arc rotating 1s linear (disable under prefers-reduced-motion, replace by a static half-filled circle); done = filled teal circle with check; failed = vermillion filled square with X; skipped = dash.
- Running row has bg `--surface-alt` #EAE4DA, others transparent; a 2px connecting line #D9D1C4 between glyphs, teal for completed segment.
- Under a running stage show one live mono line of real work ("Testing claim 7 of 23"), a real counter, never fake percentages. Claims found so far appear in a right column as they are proposed, with status chips updating in place (so "live" is visible).
- Error: stage turns into failed with reason + "Retry from this stage" pill; partial results are not shown as verified.

### Verdict badge
- Height 28px, padding 0 12px, r=999, 12/16 w600 mono caps +0.6px tracking. Always glyph + word.
- PASS: label "VERIFIED", SOLID fill #0F5C58, text #FBF9F5, check-in-circle glyph.
- REJECT: label "REJECTED", OUTLINE 1.5px #B3411B, fill #F6E3DB, text #8E2F0F, X-in-square glyph. (Fill versus outline plus glyph shape plus word means colour is never the only cue.)
- NOT_TESTABLE: label "NOT TESTABLE", dashed 1.5px #6B6458 outline, fill transparent, text #4A443A, dash-in-circle glyph.
- Tooltip/aria-label spells out the rule: "Verified: q = 0.003 is below alpha 0.05 and effect size is in the 'medium' band".
- Never show an evidence score as the verdict; badge reflects only gate result. Only VERIFIED claims get a primary-sized treatment.

### Claim card
- 24px radius, 1px border #D9D1C4, bg #FBF9F5, no shadow, padding 24px, gap 16px. Left 4px edge is NOT used (that is a slop card pattern); status is the badge in the top-right.
- Layout top to bottom: (row) mono caps claim type "GROUP DIFFERENCE" left, verdict badge right; (claim sentence) Source Serif 4 20/30 w500, hedged template text; (row) variable chips; (stat row) three mono stats with labels: "q 0.003", "effect d = 0.52 (medium)", "n = 4,812"; (footer) "Open proof" text-pill button with chevron.
- Hover: border #BFB5A5 and bg #FFFDF9; focus-visible 2px teal outline offset 2px; selected (drawer open) 2px #0F5C58 border.
- Verified claims in a main column list ordered by effect size; rejected claims in a collapsed-by-default but visible section "Rejected (N)" with reason text visible on each card ("Not significant after correction: q = 0.41"). Do not hide rejections; the reasons ARE the product.
- Density: not a uniform grid. Verified = full card (above); rejected = compact 72px row (type, sentence on one line truncated to 2, reason, badge) so hierarchy is visible.

### Proof drawer
- Right-side panel 520px wide (min(520px, 100vw) on small screens), bg #FBF9F5, left border 1px #D9D1C4, no shadow, slides in 200ms ease-out (instant under reduced motion); page content shifts, does not dim with a blur scrim.
- Sections (accordion-free, scroll with sticky header 64px): 1 Claim and verdict, 2 Test (method name, null hypothesis, n, seed logged, alpha), 3 Numbers table (raw p, q after correction, effect size + CI, band), 4 The chart of underlying data, 5 Falsification code (mono 13/20 in #F3EFE8 block, copy button, "re-run with seed 1234" note), 6 Data used (columns, rows kept/dropped), 7 Proof object JSON (collapsed).
- Header: verdict badge + short id mono, close button (36x36 pill ghost, Esc closes, focus returns to card).
- Keyboard: j/k next/prev claim while drawer open.

### Evidence / source chips (Perplexity-style citation, for data)
- Chip: height 28px, r=999, bg #EAE4DA, border 1px #D9D1C4, 12/16 mono w500, padding 0 10px, leading 14px glyph (column = hash/tag; test = beaker outline drawn as simple line icon, not sparkle).
- Examples: "col: bmi", "n=4,812", "Welch t-test", "seed 1234", "BH FDR". Clicking opens the proof drawer scrolled to the relevant section; hover shows value definition.
- Display the evidence row ABOVE the claim detail in the drawer, like Perplexity shows sources before the answer; the claim sentence uses small numbered superscripts [1][2] that map to evidence rows when it cites specific figures.

### Chart containers
- Card: 24px radius, 1px border #D9D1C4, bg #FBF9F5, padding 24px; header row with chart title 16/24 w600 and Observable-style small label chip on top-left naming purpose ("DISTRIBUTION", "GROUP COMPARISON", "SCATTER + FIT"); one-sentence takeaway beneath in text-2 14/20 saying what the chart shows (a statement, not "Chart 1").
- Plot area: direct-label series (no legend if <= 3 series), 1px gridlines #E4DDD1, axis text 12/16 mono #6B6458, axis title 12/16 #4A443A, zero baseline 1.5px #BFB5A5. Min plot height 240px, aspect 16:9 desktop, 4:3 under 480px.
- Always show n in a mono footnote. Show raw points (jittered) beneath summary marks (box/violin) so users see the data, with 0.45 opacity points.
- Under each chart a "Table view" toggle (ghost pill) that swaps to the underlying numbers; the chart has role=img with aria-label summarising the finding.
- Loading: skeleton rectangle #EAE4DA with static 8px-radius bars (no shimmer when reduced motion); error: "Chart could not be drawn: <reason>", with the proof table still shown.

### Empty / loading / error states
- Empty (history, first visit): left-aligned block, H3 18/28 plus one sentence plus a single pill action; no illustration, no mascot. Example copy shape: "No runs yet." / "Upload a file to create the first record." / [Upload a file].
- Empty results (no claim survived): this is a RESULT, not an error. Heading "No claim survived testing", subline "23 tested, 0 verified, 23 rejected" and the rejected list visible beneath.
- Loading: use real stage tracker or skeleton blocks of the final shape; no spinner-only screens longer than 400ms.
- Error: card with 1.5px #B3411B border, bg #F6E3DB, plain cause + next action; the error message is selectable mono for the technical id. Fail-closed language: "Nothing was marked verified."
- Toasts: bottom-left 360px max, 44px high pills, 4s, only for non-critical confirmations.

### Table (history, numbers)
- No zebra stripes. Header row 40px, 12/16 mono caps +0.6px #6B6458, bottom border 1px #BFB5A5; body rows 48px (compact variant 36px), 14/20, row dividers 1px #E4DDD1, no vertical lines.
- Numeric columns right-aligned, tabular-nums, mono; text left. First column sticky when scrolled horizontally.
- Row hover bg #F3EFE8 (on #FBF9F5 surface), selected row 2px inset teal border-left via box-shadow-free `border-left` inset of 2px on first cell only on selected.
- Sort indicator is a text glyph plus aria-sort. Verdict column uses badge (small, 24px variant, 11px text).
- History view: rows = runs (file name, date, rows x cols, N tested, N verified, N rejected), selecting opens the run. Memory view lists written insights (PASS only) with the run each came from and a "Remove from memory" ghost action.

### Landing page composition (Calm)
- Dark hero (#14201F) left-aligned: product name PRAMANA as wordmark 20/24 w600 in nav, H1 56/58 w500 ls -0.022em in Source Serif 4 (or Inter if serif rejected) stating the actual promise in one sentence (not "Unlock insights"); lead 18/28 #C9C4B8; right column: a REAL sample result strip (one verified claim card and one rejected claim card, labelled "Sample output") rather than abstract art.
- Alternating tones below: #F3EFE8 (how it decides: 4 steps with real thresholds listed in mono), #EAE4DA (what a rejection looks like), then dark footer #0F1817.
- Page max 1120px content, 24px gutters, section padding 96px desktop / 64px mobile.

---------------------------------------------------------------------
## (d) Anti-slop checklist (each is testable)

1. No gradient anywhere except an optional single flat-tone radial in the dark hero at <= 6% lightness delta. Test: grep CSS for `linear-gradient|radial-gradient`; every hit justified.
2. Zero purple/indigo/violet hues: no HSL hue between 250 and 300 in any token. Test: script over token file.
3. No `backdrop-filter`, no translucent card backgrounds (alpha < 1 on card/surface). Test: grep.
4. No box-shadow on cards, buttons, drawers (Calm: shadowless). Only focus rings (outline). Test: grep `box-shadow` returns 0.
5. No emoji characters anywhere in the DOM or copy; icons are a single line-icon set at 16/20px, 1.5px stroke. Test: regex over rendered text for \p{Extended_Pictographic}.
6. No sparkle/magic-wand/star icons and no "AI-powered", "magic", "unlock", "supercharge", "seamless", "insights at your fingertips" in copy. Test: copy lint wordlist.
7. No decorative blobs, orbs, mesh backgrounds, floating shapes; every non-text graphic is data or a UI control. Test: any SVG/img must have a data or functional purpose in its alt/aria.
8. Hero is left-aligned, with the visual being a real sample of the product output. Test: h1 text-align is start; the hero contains an actual claim card component.
9. No "three feature cards in a row" section; any list of features appears as numbered steps with specifics (thresholds, test names) in varying widths. Test: no section with exactly three equal-width sibling cards.
10. Not everything is centred: at most one centred element per page (e.g. a short empty-state line). Test: count elements with text-align:center <= 2.
11. Card radii come from {24px cards, 12px nested panels, 8px inputs inside cards, 999px pills/chips}; no other radii. Test: computed border-radius audit.
12. Spacing only from the 4px-based scale; no arbitrary 13px/17px paddings. Test: lint or computed-style audit against allowed set.
13. Max 7 distinct font sizes per page and 2 font families plus one mono; at most 4 text colours. Test: computed audit.
14. Verdict is never conveyed by colour alone: every PASS/REJECT/NOT_TESTABLE shows a distinct glyph shape, fill style and the word. Test: render in grayscale (filter: grayscale(1)) and confirm all three are distinguishable; plus a deuteranopia simulation.
15. Contrast: all text >= 4.5:1 (>= 3:1 for 18px+/14px bold and UI boundaries). Test: axe/Lighthouse and token-pair script.
16. No uniform card grid on the results screen: verified claims are full cards, rejected claims are compact rows, charts differ in span. Test: results container has >= 2 distinct item components.
17. No vague copy: every label names the thing (a count, a column, a test). No lorem, no "Feature 1", no placeholder lines like "Your insights here". Test: copy review plus grep for "lorem|placeholder|insights".
18. Numbers are mono, tabular, right-aligned, with units and n; p/q values shown as given (q = 0.003) with no rounding to "significant!" language. Test: `font-variant-numeric: tabular-nums` on numeric cells.
19. Loading shows real pipeline stage and counts (e.g. "Testing claim 7 of 23"), never a fake progress percentage or indefinite spinner alone. Test: no progress value not tied to a counter.
20. Motion: only 120-200ms ease-out transitions for state change, one rotating indicator on the running stage; everything respects prefers-reduced-motion; nothing loops decoratively or fires on scroll. Test: grep animations; emulate reduced motion.
21. Default blue (#2563eb, #3b82f6) and Tailwind default palette are absent. Test: grep for these hex values.
22. Rejections are first-class: the rejected list and reasons are reachable without extra clicks; no screen shows only successes. Test: results page contains a rejected section header and reason text per row.
23. No "dark mode with neon" or glow: no colour with saturation > 70% and lightness > 55% on dark surfaces. Test: token audit.
24. Every interactive element has a visible focus-visible ring and a >= 36px hit area (44px for primary). Test: Tab through page; computed sizes.
25. Charts: no 3D, no dual axis, no rainbow palettes, no pie with > 3 slices, no chart without n and axis labels. Test: chart spec lint.

---------------------------------------------------------------------
## (e) Proposed scales and tokens

### Type
Families (recommendation; swap if licensing is a concern): UI sans = Inter Variable (Linear, Observable, Julius use it, but tracking and weights below make it distinct) or Geist Sans; prose/claim/headline serif = Source Serif 4 Variable (Observable uses the same class of serif for body); mono = Geist Mono or JetBrains Mono / Spline Sans Mono for numbers, labels, code.

| Token | Size / line-height | Weight | Tracking | Use |
|---|---|---|---|---|
| display | 56 / 60 | 500 (serif) | -0.022em | landing H1 only |
| h1 | 40 / 44 | 500 | -0.02em | page titles |
| h2 | 28 / 36 | 500 | -0.015em | section titles |
| h3 | 22 / 28 | 500 | -0.01em | card/drawer titles |
| lead | 18 / 28 | 400 | 0 | hero lead, empty-state lead |
| claim | 20 / 30 | 500 (serif) | 0 | claim sentences |
| body | 16 / 24 | 400 | 0 | default |
| ui | 14 / 20 | 500 | 0 | buttons, table cells, chips text |
| small | 13 / 20 | 400 | 0 | helper, captions |
| mono-label | 11 / 16 | 500 caps | +0.08em | metadata labels, table headers |
| mono-num | 14 / 20 | 450 | 0, tabular-nums | stats |
| code | 13 / 20 | 400 | 0 | falsification code |
Weights: 400 body, 500 UI/heading, 600 only for badges and the wordmark. Mobile (<640px): display 40/44, h1 32/36, h2 24/30.

### Spacing (4px base)
4, 8, 12, 16, 24, 32, 48, 64, 96, 128 (token names s1 to s10).
- Card padding 24 (compact 16); gap inside card 16; gap between cards 16 (lists) / 24 (sections within page); gutter 24 (16 on mobile); section padding 96 desktop / 64 mobile / 128 reserved for hero only.
- Content widths: page 1120; reading column 720; results list 720 + drawer 520; wide imagery/chart 1120.
- Control heights: 28 chip/badge, 36 compact button/input, 44 standard button/input (hit area), 52 hero CTA.

### Radii
8 (inputs in cards, code blocks), 12 (nested panels, tooltips), 24 (cards, dropzone, drawer is square on the screen edge), 999 (buttons, chips, badges, tabs).

### Colour tokens (light, Calm, hex)
Surfaces
- `--bg-canvas` #F3EFE8 (greige)
- `--bg-alt` #EAE4DA (alternating band)
- `--surface` #FBF9F5 (cards, drawer)
- `--surface-sunken` #F3EFE8 (code blocks, table hover)
- `--hero` #14201F (dark hero; warm dark teal-black)
- `--footer` #0F1817
Borders
- `--border` #D9D1C4 (cards, dividers, 1px)
- `--border-soft` #E4DDD1 (table rows, gridlines)
- `--border-strong` #BFB5A5 (dropzone, baseline, hover)
Text on light
- `--text-1` #1F1C17 (about 15:1 on canvas)
- `--text-2` #4A443A (about 8:1)
- `--text-3` #6B6458 (about 5:1 on #F3EFE8; do not use below 13px bold-less on #EAE4DA, where it drops near 4.4:1, use text-2 there)
Text on dark
- `--on-dark-1` #EDEAE2, `--on-dark-2` #C9C4B8, `--on-dark-3` #9A9488 (use >= 16px or bold only)
Accent (deep teal)
- `--accent` #0F5C58 (about 7.4:1 on surface), `--accent-hover` #0B4744, `--accent-press` #083937, `--accent-tint` #D6E8E4, `--accent-on-dark` #5FC4B5 (links/CTA on hero; passes on #14201F), button text on accent #FBF9F5.
Status
- `--pass` #0F5C58 (same family as accent; glyph and fill style separate it from plain actions; alternative if you want pass distinct from buttons: #1F6B8A is NOT recommended because it drifts blue)
- `--reject` #B3411B (4.9:1 on surface), `--reject-tint` #F6E3DB, `--reject-ink` #8E2F0F
- `--neutral` #6B6458 for NOT_TESTABLE and pending
- `--focus` #0F5C58 2px outline, 3px offset (and #5FC4B5 on dark)
Grayscale check: #0F5C58 (L approx 33) vs #B3411B (L approx 45) differ in luminance, and the badge fill style/glyph differ too.

### Chart palette (colour-blind safe, reserved vermillion for REJECT only)
Categorical (ordered; derived from Okabe-Ito hue spacing, adjusted for the warm surface and distinct luminance steps):
1. #0F5C58 teal (primary group / "the data under test")
2. #C47A1E amber (comparison group)
3. #3F6FB5 mid blue
4. #A64D79 muted magenta-rose
5. #6B6458 neutral grey (baseline, "all others")
6. #7FB8AE light teal (CI band at 35% opacity, secondary)
Rules: two-group comparisons always use 1 and 2 (differ in hue AND lightness: about L33 vs L58); never more than 5 series; add direct labels plus a marker shape or dash style per series (circle, square, diamond; solid, dashed) so charts survive grayscale.
Sequential (single variable intensity): #E3EFEC, #B5D6CF, #7FB8AE, #3F8C84, #0F5C58.
Diverging (effect direction, centre = no effect): #B3411B, #E3A58E, #F3EFE8, #7FB8AE, #0F5C58 (vermillion to teal, safe for deuteranopia/protanopia because luminance rises monotonically toward the centre and the end hues differ in both axes).
Chart chrome: gridlines #E4DDD1, axis line #BFB5A5, axis text #6B6458 at 12px mono, point opacity 0.45, mean marker #1F1C17.
Reference cue for rejected claims' charts: use the neutral palette (#6B6458 plus light grey) so a rejected claim never looks like a verified one at a glance.

### States summary
- Button primary: #0F5C58 bg, #FBF9F5 text, 44px, r=999; hover #0B4744; press #083937; disabled #BFB5A5 bg / #6B6458 text; focus outline 2px #0F5C58 offset 3px. Secondary: transparent, 1px #BFB5A5, text-1; hover bg #EAE4DA. Ghost: no border, text-2.
- Input: 44px, r=8, 1px #BFB5A5 on #FBF9F5; focus 2px #0F5C58; error 1.5px #B3411B plus message; placeholder #6B6458.
- Link: #0F5C58 underline 1px offset 3px (not colour only).

---------------------------------------------------------------------
## Five-line synthesis
1. Quality sites use a tiny type scale with negative display tracking, odd variable weights, and grey steps for hierarchy, not colour.
2. Accent is rare; flat bordered cards, 4-6px (Calm: 24px) radii, hairline borders, no shadows.
3. Left-aligned asymmetric heroes that show the real product; Grid (dark green + one mint CTA) is the closest precedent for Calm.
4. Mono caps micro-labels carry metadata (Hex, Grid, Observable): use them for stats, stages, evidence chips.
5. Evidence-before-answer (Perplexity pattern, prior knowledge) maps to claim -> evidence chips -> proof drawer; rejections shown with reasons.
