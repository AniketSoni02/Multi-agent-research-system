---
version: "superdesign-alpha"
name: "Liquid Blue Glass"
description: "Near-black documentation-grade dark system with a single rationed blue accent, blur-first glass panels, and system-sans type stepped in tight, restrained increments."
colors:
  background: "#08090C"
  surface: "#0D1016"
  surface-secondary: "#11151D"
  text-primary: "#F4F6FA"
  text-secondary: "#A0A7B4"
  text-muted: "#6F7785"
  accent: "#4F8FFF"
  border: "#BFDCFF"
  success: "#50C58D"
  warning: "#DFAE52"
  danger: "#E05D66"
typography:
  display-lg:
    fontFamily: "-apple-system"
    fontSize: "40px"
    fontWeight: 600
    lineHeight: "1.1"
    letterSpacing: "-1.8px"
  headline-md:
    fontFamily: "-apple-system"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: "1.4"
  body-md:
    fontFamily: "-apple-system"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: "1.33"
  label-md:
    fontFamily: "-apple-system"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: "1.56"
  body-regular:
    fontFamily: "-apple-system"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "1.5"
  eyebrow-mono:
    fontFamily: "-apple-system"
    fontSize: "12px"
    fontWeight: 600
    letterSpacing: "0.06em"
spacing:
  base: "4px"
  scale: "4, 8, 12, 16, 20, 24, 32, 40, 48, 64"
  gap: "32px"
  section-padding: "32px"
rounded:
  control: "12px"
  card: "28px"
  panel: "18px"
  pill: "9999px"
  hairline: "2px"
components:
  button-primary:
    background: "rgba(96, 165, 250, 0.09)"
    text-color: "#F4F6FA"
    radius: "9999px"
    height: "40px"
    padding: "0px 16px"
    border: "1px solid rgba(191, 219, 254, 0.24)"
    shadow: "rgba(74, 144, 255, 0.075) 0px 0px 24px 0px"
  button-secondary:
    background: "rgba(96, 165, 250, 0.07)"
    text-color: "#F4F6FA"
    radius: "9999px"
    height: "40px"
    padding: "0px 12px"
    border: "1px solid rgba(191, 219, 254, 0.14)"
  button-ghost:
    background: "rgba(255, 255, 255, 0.06)"
    text-color: "#F4F6FA"
    radius: "9999px"
    height: "32px"
    padding: "0px 12px"
    border: "none"
  button-destructive:
    background: "#E05D66"
    text-color: "#FFFFFF"
    radius: "9999px"
    height: "40px"
    padding: "0px 16px"
    border: "none"
  card-glass:
    background: "transparent"
    backdrop-filter: "blur(18px) saturate(1.05)"
    radius: "28px"
    padding: "32px"
    shadow: "rgba(0, 0, 0, 0) 0px 0px 0px 0px, rgba(0, 0, 0, 0) 0px 0px 0px 0px, rgba(255, 255, 255, 0.043) 0px 1px 0px 0px inset, rgba(0, 0, 0, 0.18) 0px 16px 48px 0px"
  navbar:
    background: "#08090C"
    backdrop-filter: "blur(40px)"
    height: "81px"
    width: "100%"
    radius: "0px 0px 0px 0px"
---
# Liquid Blue Glass
Source: https://p.superdesign.dev/draft/50d6bee9-95da-4dce-a52d-b28735f7e9c8

## Overview
This is a dark-mode-default documentation aesthetic built for interface specification itself: a near-black canvas carries liquid-glass panels, a single blue accent rationed to interactive elements, and system-sans typography stepped in small, deliberate increments (12/14/18/20/40px). It reads as Swiss-adjacent restraint filtered through macOS-style glassmorphism — no gradients as decoration, no illustration, no photography. Every visual choice (blur, radius, spacing) is itself a labeled design token, making the page a literal token gallery as much as a page.

## Composition
The first screen opens with a compact 81px navbar, then a two-column foundations spread: a wide glass card stating the system's premise on the left, a narrower "core geometry" spec card on the right — establishing the page's core rhythm of pairing a narrative panel with a data/spec panel. Below, a full-width semantic color swatch row (7 tiles) breaks the two-column pattern as a spanner. The page then proceeds in a steady cadence of paired 2-column glass card rows (typography+buttons, form controls+status, surface hierarchy+do/don't, overlays+responsive layout, modal+sheet, upload+status list), occasionally interrupted by full-width spanners (color palette strip, status system row, definition-of-done band, closing 3-up card row). Density is high and text-forward: nearly every card is filled edge-to-edge with labeled specimens (swatches, sliders, chips, form fields) rather than open whitespace. The deliberate choice is exhaustive token-by-token enumeration over a sparse marketing-style hero — it rejects big single-statement visuals in favor of a dense reference-manual layout, trading breathing room for completeness.

## Colors
The pixel field confirms a near-black stage: `#181818`-family darks (~48%) and near-black navy `#000018` (~36%) dominate, with true black (~10%) at the deepest recesses — this is the `background`/`surface` duo, measured as `#08090C` (canvas) and `#0D1016`/`#11151D` (primary/secondary panel fills). White (`#FFFFFF`) occupies a full 32.4% of declared area, but this is text and borders, not background — headlines, labels, and card outlines, never a fill. The single brand accent is `#4F8FFF` (declared as `action.primary`, ring token `--tw-ring-color: #3C81F5`), rationed almost entirely to interactive chrome: button fills at low alpha (`rgba(96,165,250,0.07–0.09)`), focus rings, progress bars, and a handful of link-toned labels. Status colors are semantic and equally rationed: `#50C58D` success, `#DFAE52` warning, `#E05D66` danger/destructive — each confined to a badge, icon, or single button. Everything structural (dividers, secondary surfaces, card chrome) is deliberately left uncolored, rendered only in grayscale tones (`#F4F6FA` primary text, `#A0A7B4` secondary, `#6F7785` muted) so the blue and semantic hues read as pure signal against a monochrome field.

## Typography
A single system-sans family (`-apple-system`) carries the entire hierarchy with no serif or display face anywhere — consistent with the system's own stated typography rule. Display headlines sit at 40px/600, line-height 1.1, tracked tight at -1.8px. Section titles step down to a headline-md 20px/600/1.4, sub-headlines around 18px/600/1.56 (label-md), and a compact 12px/600/1.33 mode covers dense UI labels and captions. Running body copy is lighter and smaller than any of the bold labels — 14px/400 in `#A0A7B4` — creating hierarchy through weight-contrast (nearly everything structural is 600 semibold) rather than size-contrast alone. Eyebrows are short, all-caps, blue-tinted labels sitting above every card headline.

## Layout
Content is bounded to a 1320px max-width page and a narrower 1168px navigation max-width. The base grid unit is 4px, with a working spacing scale of 4·8·12·16·20·24·32·40·48·64px — card gaps consistently measure 32px. The dominant grid type is a strict 2-column card grid, gap 32px, with asymmetric row splits (39/58, 56/41, 56/41 — never an even 50/50), meaning paired cards are intentionally unequal in width to weight narrative copy against spec/data density. Full-bleed spanners break this grid at intervals: the color-swatch row (7-across), status system rows, and closing rows. Corner radii scale by container level: 12px small controls, 18px mid panels, 28px large glass cards, up to 9999px pills — never a single flat radius across all levels. Responsively the system collapses columns before compressing content: 12 columns/32px padding at 1440px desktop, 8 columns/24px at 768px tablet, 4 columns/16px at 390px mobile, with no horizontal scroll and two-line text wrapping preferred over truncation.

## Components
- **Navbar**: edge-to-edge square bar, 0 corner radius on all four corners, 81px tall, full 1920px viewport width (0px inset either side), fill `#08090C` with `backdrop-filter: blur(40px)`, static/non-scrolling in the captures.
- **Button — primary (prominent glass)**: pill radius 9999px, 40px height, padding 0 16px, fill `rgba(96, 165, 250, 0.09)`, border `1px solid rgba(191, 219, 254, 0.24)`, text `#F4F6FA`; appears as the leading action in modal/form footers (e.g. "Save changes" role).
- **Button — secondary glass**: pill 9999px, 40px height, padding 0 12px, fill `rgba(96, 165, 250, 0.07)`, border `1px solid rgba(191, 219, 254, 0.14)`, text `#F4F6FA`; used for lower-emphasis actions beside the primary, and for the navbar's own utility control (the "hover/focus/uploading" state row visible mid-page uses this variant, not the primary).
- **Button — ghost**: pill 9999px, 32px height, padding 0 12px, fill `rgba(255,255,255,0.06)`, no border; used for cancel/dismiss actions beside a primary or secondary.
- **Button — destructive**: pill 9999px, filled solid `#E05D66`/red, white text; single instance per context (delete/remove actions), never doubled with the ghost/secondary red outline seen in menus.
- **Glass card (repeating family, ×10+)**: transparent fill, `backdrop-filter: blur(18px) saturate(1.05)`, radius 28px, padding 32px, shadow `rgba(0,0,0,0) 0px 0px 0px 0px, rgba(0,0,0,0) 0px 0px 0px 0px, rgba(255,255,255,0.043) 0px 1px 0px 0px inset, rgba(0,0,0,0.18) 0px 16px 48px 0px`; anatomy top-to-bottom: small all-caps blue eyebrow label, bold headline, short body sentence, then one of: a token swatch row, a slider/scale visualization, a form-field pair, a status list, or a small stat/count block. This card is the system's single dominant content unit, reused for every 2-column section.
- **Color swatch tile (×7, full-width row)**: square-ish tiles, dark or saturated fill matching the named token, rounded corners (~12–16px), label + hex stamped bottom-left inside the tile.
- **Form field**: label always visible above input, 44px-tall input, 12px radius, `#11151D`-toned fill, focus state shown via a full blue ring border; error state swaps border/label to `#E05D66` with an inline helper message below.
- **Status row / list item**: leading icon (colored by semantic state), bold title + muted subtitle stacked, trailing status word or small action button; success rows in green, warning in amber, error in red, all on the same neutral row background.
- **Progress bar**: thin rounded track, `#4F8FFF` or `#50C58D` filled bar, percentage or fraction label right-aligned.
- **Badge/chip (status, tag, count)**: pill radius, low-alpha tinted fill matching its semantic color, small icon + label; neutral metadata chips use plain gray fill with no icon.
- **Modal (desktop)**: glass panel, ~560px width, fixed header (title + close) and fixed footer (cancel + primary button), scrolling body between; larger corner radius than standard cards.
- **Sheet (mobile)**: same glass component re-scaled to 390px viewport, 24px top-corner radius only, drag handle at top, safe-area-aware stacked buttons at bottom.
- **Popover / menu / tooltip / toast (anchored overlay family)**: shared glass treatment at varying sizes (popover 280–360px, menu 220–280px, toast 360–420px), 8px anchor gap, 12px viewport padding; menus stack plain-text items with a red destructive item at the bottom.
- **Dropzone**: large dashed-edge glass rectangle, centered upload icon, bold title + muted instruction line, secondary button beneath.
- **Stepper**: horizontal segmented track, completed segments filled solid, current segment lighter/outlined, upcoming segments dim; labels below each segment.

## Graphics & Effects
Two full-page gradients are hairline grid overlays, not color washes: `linear-gradient(rgba(255,255,255,0.01) 1px, transparent 1px)` and its 90°-rotated pair, forming a barely-visible 1px dot/line grid texture across the entire canvas — this is the system's only "background pattern," read as a faint technical grid rather than an image. Three small radial/linear gradients are confined to isolated decorative elements covering under 0.5% of the page each: a blue radial wash `radial-gradient(circle at 72% 20%, rgba(79,143,255,0.42), transparent 36%)` and a navy radial `radial-gradient(circle at 20% 76%, rgba(37,55,88,0.58), transparent 45%)`, both likely seated inside small icon tiles or accent corners, plus a diagonal panel gradient `linear-gradient(145deg, rgb(23,31,49), rgb(8,9,12) 68%)` used as a single card or icon-badge fill — none of these should be stretched across the hero or any full section. Card elevation reads entirely through blur and soft shadow, never harsh drop shadows: `blur(18–40px)` backdrop filters plus a paired inset highlight (`rgba(255,255,255,0.043) 0px 1px 0px inset`) and diffuse drop (`rgba(0,0,0,0.18) 0px 16px 48px`) simulate frosted glass floating a few pixels above the canvas.

## Motion
Interaction timing is explicit and fast: transitions run on `border-color, box-shadow 0.2s` and `cubic-bezier(0.22, 1, 0.36, 1)` easing for standard state changes, with a quicker `opacity 0.1s ease-in` for simple fades. Documented rhythm is three-tier: 120ms for fast micro-feedback, 200ms standard, 260ms for overlay entrances. Pressed states scale to 0.98. Loading states use continuous `spin`/`system-spin` keyframes for indeterminate spinners and `pulse` for skeleton placeholders. Reduced motion is treated as mandatory, not optional.

## Guardrails
- Never fill a full section or hero with the small radial/diagonal gradients — they belong to single icon tiles or corner accents only, at under 1% page coverage.
- Never render two glass panels directly stacked with no gap ("glass-on-glass") — always separate with canvas space or a section divider.
- Never substitute a flat solid card fill for the blur+inset-highlight+soft-shadow glass recipe; elevation must come from blur, not opacity or heavy drop shadow.
- Keep the blue accent confined to interactive/action elements and rings — do not tint structural chrome, dividers, or body text blue.
- Do not flatten the 2-column card grid to even 50/50 splits; rows are intentionally asymmetric (e.g. 39/58, 56/41).
- Do not swap the system-sans face for a serif or display font anywhere, including eyebrows or numerals.