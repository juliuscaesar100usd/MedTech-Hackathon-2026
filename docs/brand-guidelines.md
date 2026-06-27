# Brand Guidelines v1.0 — MedArchive

> **MedArchive** turns clinic price-lists (PDF, scans, Excel, Word) into one
> searchable, versioned catalog of medical services and prices. The brand must
> read **precise, credible, and calm** — a clinical instrument, not a marketing
> site. Every choice below serves trust and legibility first.
>
> This document is the single source of truth. The live implementation lives in
> `frontend/src/styles.css` (`:root` tokens); a portable export is mirrored in
> `frontend/assets/design-tokens.json`.

## Quick Reference

- **Primary Color:** #0e7490 (clinical cyan / teal-700)
- **Accent Color:** #0e7490 (links & interactive text — same hue, locked)
- **Display Font:** Manrope
- **Body Font:** Inter
- **Voice:** Precise · Credible · Plain-spoken

---

## 1. Color Palette

The whole product runs on **one brand hue** — clinical cyan — over a slate
neutral base. There is no second decorative accent (an earlier blue `#2563eb`
was removed). Blue survives only as the functional **info** state.

### Primary Colors
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Clinical Cyan (teal-700) | #0e7490 | rgb(14,116,144) | Primary brand color: CTAs, links, headings accent, logo |
| Cyan-600 | #0891b2 | rgb(8,145,178) | Lighter end of the brand gradient; fills, borders, icon strokes (non-text) |
| Cyan-800 (dark) | #155e75 | rgb(21,94,117) | Pressed/active states, dark gradient stop |

### Accent Colors
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Accent (teal-700) | #0e7490 | rgb(14,116,144) | Hyperlinks and interactive text. Locked to the primary hue — one accent across the product |
| Accent Tint | #ecfeff | rgb(236,254,255) | Hover/selected wash, subtle highlight backgrounds |

> **Why teal-700 and not the brighter cyan-600 for text?** cyan-600 on white is
> only 3.68:1 — it fails WCAG AA for body-size text. teal-700 is 5.36:1 and
> passes. The bright cyan is reserved for fills, borders, and icon art, never
> for small text.

### Neutral Palette
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Background | #f4f7fb | rgb(244,247,251) | Page background |
| Surface | #ffffff | rgb(255,255,255) | Cards, tables, nav |
| Surface-2 | #f8fafc | rgb(248,250,252) | Inset/zebra surfaces |
| Border | #e2e8f0 | rgb(226,232,240) | Dividers, card borders |
| Border Strong | #cbd5e1 | rgb(203,213,225) | Inputs, emphasized edges |
| Text Primary | #0f172a | rgb(15,23,42) | Body text (~16:1 on surface, AAA) |
| Text Muted | #64748b | rgb(100,116,139) | Captions, secondary labels |
| Text Faint | #94a3b8 | rgb(148,163,184) | Placeholders, disabled |

### Semantic Colors
| Name | Hex | Background | Usage |
|------|-----|-----------|-------|
| Success | #059669 | #ecfdf5 | Verified prices, valid states |
| Warning | #b45309 | #fffbeb | Price anomalies (>50% jump), needs-review |
| Danger | #dc2626 | #fef2f2 | Validation errors, destructive actions |
| Info | #0369a1 | #f0f9ff | Neutral notices (the only sanctioned blue) |

### Accessibility
- Body text on surface: **~16:1** (WCAG AAA).
- Primary CTA — white on teal-700: **5.36:1** (AA).
- Links — teal-700 on white: **5.36:1** (AA).
- All interactive elements meet WCAG 2.1 AA. Functional color is never the only
  signal — pair with icon or label (e.g. verified badge, anomaly tag).

---

## 2. Typography

Two self-hosted variable families, both carrying **full Cyrillic (ru + kz)** —
the hard requirement for this product. Files in `frontend/public/fonts/`,
subset by script, `font-display: swap`.

### Font Stack
```css
--font-display: 'Manrope', 'Inter', system-ui, sans-serif;   /* headings, wordmark, big numbers */
--font-sans: 'Inter', system-ui, sans-serif;                 /* body, UI, data tables */
--font-mono: ui-monospace, SFMono-Regular, Menlo, monospace; /* code: thresholds, status keys */
/* role aliases (same values) for tooling that keys on heading/body: */
--font-heading: 'Manrope', 'Inter', system-ui, sans-serif;
--font-body: 'Inter', system-ui, sans-serif;
```

Manrope gives headings presence and precision; Inter is the legibility workhorse
for dense price tables and small UI text. Prices and metrics use
`font-variant-numeric: tabular-nums` so columns stay aligned.

### Type Scale
| Element | Font | Weight | Size (Desktop/Mobile) | Line Height |
|---------|------|--------|----------------------|-------------|
| Hero H1 | Manrope | 800 | 46px / 30px | 1.05 |
| H1 | Manrope | 700 | 28px / 24px | 1.2 |
| H2 | Manrope | 700 | 21–34px | 1.15 |
| H3 | Manrope | 700 | 17px | 1.3 |
| Metric value | Manrope | 800 | 38px / 28px | 1.0 |
| Body | Inter | 400 | 15px | 1.55 |
| Small / label | Inter | 600 | 12–14px | 1.4 |
| Price / data | Inter (tabular) | 700 | inherit | — |

Headings carry `letter-spacing: -0.018em` to -0.02em for a tight, engineered feel.

---

## 3. Logo Usage

The mark is a **clinical cross over a faint shelf line** on a teal-gradient chip:
the cross carries the *medical* meaning, the wordmark "MedArchive" carries
*archive*. Source: `frontend/public/logo.svg` (also the favicon); the nav renders
the same geometry inline (`BrandMark` in `components/Layout.tsx`).

### Variants
- **Primary:** chip mark + "MedArchive" wordmark (Med in ink, **Archive** in teal).
- **Icon:** chip mark only — favicon, app icon, square spaces.
- **Monochrome:** white mark on teal, or teal mark on white for limited palettes.

### Clear Space & Size
- Clear space ≥ the height of the chip on all sides.
- Minimum chip size: 24px digital. Wordmark lockup: 96px width minimum.

### Don'ts
- Don't recolor the chip outside the teal palette or add a second hue.
- Don't add shadows/effects to the glyph (the chip's own `--shadow-sm` is enough).
- Don't rotate, skew, stretch, or rebuild the cross proportions.
- Don't set the wordmark in any font but Manrope.
- Don't place the mark on a busy or low-contrast background.

---

## 4. Voice & Tone

MedArchive speaks **Russian-first** (ru, with kz/en support). It is the voice of
a careful records clerk, not a salesperson. State facts, show the data, get out
of the way.

### Brand Personality
Precise (Точный): exact numbers, named sources, no rounding away meaning.
Credible (Достоверный): every price is versioned and traceable; never overclaim.
Plain-spoken (Понятный): plain Russian, no jargon walls, no hype.

### Voice Chart
| Trait | We Are | We Are Not |
|-------|--------|------------|
| Precise | "93.9% авто-нормализация" | "почти всё распознаётся идеально" |
| Credible | "цена версионируется при каждой загрузке" | "самые точные цены в стране" |
| Plain-spoken | "Поиск в каталоге" | "Революционный AI-движок поиска" |
| Calm | states the result | manufactures urgency |

### Tone by Context
| Context | Tone | Example |
|---------|------|---------|
| Marketing | confident, factual | "Прайс-листы клиник — единая база услуг и цен" |
| Empty state | helpful, specific | "Для этого партнёра ещё не загружено ни одной позиции." |
| Error | clear + recovery path | "Не удалось загрузить прайс-лист. Повторить?" |
| Success | brief, factual | "Цена подтверждена и сохранена." |

### Prohibited Terms
- "революционный" / "уникальный" / "лучший в мире" (unverifiable hype)
- "успейте" / "только сегодня" (manufactured urgency — no place in a B2B tool)
- Medical advice or diagnosis phrasing (MedArchive aggregates *prices*, it does
  not advise on treatment)
- English em-dash in Russian copy — use the Russian тире (—) per locale rules

---

## 5. Imagery & Iconography

### Product Imagery
- Real product screenshots only (the operator dashboard, the catalog search).
  No stock photos of doctors, no abstract "AI" renders.
- Pipeline/cascade concepts are shown as clean SVG diagrams in brand teal
  (`/assets/pipeline.svg`, `/assets/normalization.svg`), not photography.

### Icons
- Library: **Phosphor** (`@phosphor-icons/react`), `duotone` for feature glyphs,
  `bold` for inline affordances. One family across the product — no mixing.
- Base grid 24px; brand teal or `currentColor`. No emoji as icons.

---

## 6. Motion

Trust-first means restrained motion (MOTION ~4/10).
- **Page transitions:** `route-in` — 8px rise + fade, 0.4s, on every route.
- **Scroll reveal:** content blocks fade + rise (18px) as they enter the
  viewport; grid cards/metric tiles stagger ~60ms; standalone sections no delay.
- All motion is gated behind `prefers-reduced-motion` and fails open (JS adds the
  hidden state, so reduced-motion / no-JS render fully visible).
