# Design System: Technical Precision & Editorial Clarity

## 1. Overview & Creative North Star
**Creative North Star: The Silicon Blueprint**
In the world of semiconductor and process analytics, data isn't just information—it’s a physical map of microscopic complexity. This design system departs from generic "SaaS Blue" templates to embrace a high-end editorial aesthetic that feels like a precision-engineered schematic. 

By leveraging **Space Grotesk** for structural headlines and **Inter** for data density, we create a rhythmic tension between "technical machinery" and "human legibility." The layout breaks the traditional rigid grid by using **intentional asymmetry** and **tonal layering** instead of heavy borders, allowing the user to navigate high-density datasets with zero cognitive friction. We are building a digital "clean room": sterile, precise, and authoritative.

---

## 2. Colors & Surface Philosophy
The palette is rooted in professional lithography—cool grays and deep blues punctuated by high-signal status indicators.

### The "No-Line" Rule
To achieve a premium feel, **1px solid borders are strictly prohibited for sectioning.** Boundaries must be defined through background shifts.
- Use `surface-container-low` for the main canvas.
- Use `surface-container-lowest` for primary data modules to create a "lifted" feel.
- Use `surface-container-high` for sidebars or recessed utility panels.

### Surface Hierarchy & Nesting
Treat the UI as a series of stacked, precision-cut silicon wafers.
- **Level 0 (Background):** `surface` (#f8f9fa)
- **Level 1 (Sections):** `surface-container-low` (#f1f4f6)
- **Level 2 (Cards/Modules):** `surface-container-lowest` (#ffffff)
- **Level 3 (Popovers/Modals):** `surface-bright` with Glassmorphism.

### The "Glass & Gradient" Rule
For high-priority analytics or "Active State" hero modules, apply a subtle linear gradient: `primary` (#005db6) to `primary-dim` (#0051a1) at a 135° angle. Floating tooltips should use `surface-container-lowest` with an 80% opacity and a `20px` backdrop-blur to maintain context of the data underneath.

---

## 3. Typography
We use typography as a structural element, not just for content.

*   **Structural Headlines (Space Grotesk):** Used for Page Titles (`display-sm`) and Module Headers (`headline-sm`). The geometric nature of Space Grotesk mirrors the precision of semiconductor paths.
*   **Data & Action (Inter):** All tabular data, labels, and chat components use Inter. 
    *   `label-sm` (0.6875rem) is our workhorse for high-density telemetry.
    *   `title-sm` (1rem) provides an authoritative weight for data categories.

**Hierarchy Tip:** Always use `on-surface-variant` (#586064) for metadata and units (e.g., "nm", "ms", "temp") to keep the primary `on-surface` (#2b3437) values as the focal point.

---

## 4. Elevation & Depth
Traditional drop shadows feel "heavy." We use **Tonal Layering** and **Ambient Light.**

*   **The Layering Principle:** Instead of shadows, nest a `#ffffff` card inside a `#f1f4f6` container. The contrast provides all the "lift" required.
*   **Ambient Shadows:** For floating nodes or "Critical Anomaly" popups, use a multi-layered shadow: `0 4px 20px rgba(43, 52, 55, 0.04), 0 8px 40px rgba(43, 52, 55, 0.08)`.
*   **The Ghost Border Fallback:** If high-density data tables require separation, use `outline-variant` (#abb3b7) at **15% opacity**. It should be felt, not seen.

---

## 5. Components

### Data Tables (The High-Density Core)
*   **Row Height:** 32px (Compact).
*   **Separation:** No horizontal lines. Use `surface-container-low` on `:hover` and `surface-container-lowest` as the base.
*   **Typography:** Use `label-md` for numerical data, aligned right to ensure decimal points line up.

### Graph Nodes (Process Flow)
*   **Style:** Rectangular with `rounded-sm` (0.125rem). 
*   **Status Tints:** Anomaly nodes use a `tertiary-container` (#fe4e49) background with a `tertiary` (#bb1b21) 2px left-accent bar. 
*   **Connections:** Use `outline-variant` at 40% opacity for "normal" paths; use `primary` for the "active process path."

### Chat & Collaboration (Technical Support)
*   **Bubbles:** Use `surface-container-highest` for others and `primary-container` for the user.
*   **Shape:** `rounded-md` (0.375rem). Avoid the overly "bubbly" consumer look. 
*   **Density:** Use `body-sm` for chat text to maximize message history visibility.

### Buttons & Inputs
*   **Primary Button:** `primary` (#005db6) background with `on-primary` text. Use `rounded-sm` for a technical, tool-like feel.
*   **Input Fields:** `surface-container-lowest` background with a `ghost-border` (15% outline-variant). On focus, transition the border to `primary` at 100% opacity.

---

## 6. Do’s and Don’ts

### Do
*   **DO** use whitespace (Scale `4` or `5`) to group related sensor data rather than drawing boxes.
*   **DO** use `tertiary` (#bb1b21) sparingly. It is a high-alert color for process anomalies; overusing it devalues its urgency.
*   **DO** use the `0.5` spacing (0.1rem) for micro-adjustments in complex node graphs.

### Don’t
*   **DON'T** use `full` rounding (pills) for anything other than status tags. It breaks the "technical schematic" aesthetic.
*   **DON'T** use 100% black (#000000) for text. Use `on-surface` (#2b3437) to maintain a premium, low-strain reading experience.
*   **DON'T** allow cards to have distinct borders. Let the shift from `surface-container-low` to `surface-container-lowest` do the work.