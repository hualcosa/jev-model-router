# Public visual assets

Explanatory artwork, not a benchmark or a terminal capture. No model scores,
performance claims, private tasks or deployment evidence are depicted.

## Files

- `routing-overview.svg` — architecture overview; adaptive light/dark palette.
- `routing-flow.svg` — eligibility, classification, policy and unchanged fallbacks.
- `routing-overview-mobile.svg`, `routing-flow-mobile.svg` — vertical 390-unit
  canvases for responsive image embeds; minimum type 16 units (14.69 CSS px
  at a 358px README content width).
- `social-preview.png` — 1280 × 640 link-card image, under 1 MB; not uploaded.
- Matching `.html` files — editable, self-contained originals. Open locally;
  wide diagrams scroll inside their own container on small screens.
- `generate-visuals.py` — standard-library generator for the HTML originals.

## Identity and accessibility

Project-local editorial teal/ink identity, selected with user-delegated judgment.
Light paper `#e8f0ef`, ink `#10191d`, accent `#176852`; dark paper `#10191d`,
ink `#e8f0ef`, accent `#87d8be`. System-font mode makes no external requests:
Instrument Serif → Georgia/serif; Geist → system sans; Geist Mono → system mono.
Fallback rendering is intentional and was inspected. No global skill profile
or installed style guide is changed. SVG title/description IDs and definitions
are namespaced by the packaged exporter.

Suggested embedding descriptions:

- Overview: “The main session stays unchanged while eligible delegated work
  passes through Jev classification and local model-and-effort policy, then
  reaches native Claude Code or Codex workers.”
- Flow: “Eligibility and consent precede classification. Safe supported routes
  select model and effort; explicit choices, abstention and failures preserve
  the original request.”
- Social card: “Jev Model Router: keep the orchestrator, route the work.
  Delegate a task, classify requirements, and route a native worker.”

The standalone SVGs follow the viewer's preferred color scheme. Readable-width
HTML originals provide local scrolling; GitHub scales image embeds to its
content width. Select the vertical mobile SVGs below 600px with a `picture`
source, retain the desktop SVG as the fallback image, and include a full-size
link. Adjacent README prose/alt text must retain the same meaning.
GitHub rendering itself has not been tested on a published remote page.

## Regenerate

Run `python3 assets/public/generate-visuals.py`. With the diagram-design skill
installed, use its packaged helpers (replace `$DIAGRAM_SKILL` with that install):

```sh
python3 "$DIAGRAM_SKILL/scripts/export_svg.py" assets/public/routing-overview.html assets/public/routing-overview.svg --system-fonts
python3 "$DIAGRAM_SKILL/scripts/export_svg.py" assets/public/routing-flow.html assets/public/routing-flow.svg --system-fonts
python3 "$DIAGRAM_SKILL/scripts/export_svg.py" assets/public/routing-overview-mobile.html assets/public/routing-overview-mobile.svg --system-fonts
python3 "$DIAGRAM_SKILL/scripts/export_svg.py" assets/public/routing-flow-mobile.html assets/public/routing-flow-mobile.svg --system-fonts
python3 "$DIAGRAM_SKILL/scripts/export_png.py" assets/public/social-preview.html assets/public/social-preview.png 1
python3 "$DIAGRAM_SKILL/scripts/self_check.py" --offline assets/public/routing-overview.html
python3 "$DIAGRAM_SKILL/scripts/self_check.py" --offline assets/public/routing-flow.html
python3 "$DIAGRAM_SKILL/scripts/self_check.py" --offline assets/public/social-preview.html
python3 "$DIAGRAM_SKILL/scripts/self_check.py" --offline assets/public/routing-overview-mobile.html
python3 "$DIAGRAM_SKILL/scripts/self_check.py" --offline assets/public/routing-flow-mobile.html
```

PNG export requires Playwright and an available Chromium browser. Do not change
runtime settings or activate a provider to regenerate these static assets.
