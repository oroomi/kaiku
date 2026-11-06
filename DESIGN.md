# Design (decided before the first screen; never unaided)

## Three references (URLs or screenshots in docs/refs/)
1. <reference, what we take from it: layout / density / colour>
2. <reference>
3. <reference>

## Direction (one)
<e.g. "dense data table with one accent, like a trading terminal, not a marketing site">

## Rules
- Component library defaults: <shadcn/ui | Pico.css>. System font stack. One accent colour: <hex>. Neutral greys.
- Layout: single column on mobile, max-width 1100px on desktop, 16px gutters, 8px spacing scale.
- Every screen shows real data. Empty state says "no data for <x>", nothing invented.
- Text: sentence case, short labels, no emoji, no exclamation marks.
- Motion: none except loading indicators.

## Screens
| Screen | Purpose | Reference used |
|---|---|---|
| | | |

## Review loop
Every task ends with shot.py desktop + mobile, and the builder reads both PNGs against these rules.
