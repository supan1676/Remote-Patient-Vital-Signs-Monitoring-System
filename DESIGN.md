---
name: "PulseCare"
description: "A mineral-white field atlas for clinician review of local patient measurements."
colors:
  bg: "#fafbf9"
  paper: "#fff"
  sidebar: "#f2f5f0"
  text: "#26332d"
  muted: "#5e6d63"
  faint: "#89948c"
  line: "#e2e8df"
  soft: "#f5f7f3"
  green: "#285a43"
  green-hover: "#1c4532"
  wash: "#eaf1e4"
  green-light: "#dce8d0"
  purple: "#8563a7"
  blue: "#4f7caa"
  ochre: "#a5782c"
  red: "#ac4444"
  amber: "#855914"
  amber-bg: "#faf2e0"
  dark-bg: "#171d19"
  dark-paper: "#202821"
  dark-sidebar: "#1b231d"
  dark-text: "#e2e9df"
  dark-muted: "#adb9aa"
  dark-faint: "#8a9a87"
  dark-line: "#384338"
  dark-soft: "#263028"
  dark-green: "#a5c992"
  dark-green-hover: "#c0ddb1"
  dark-wash: "#2c392a"
  dark-green-light: "#3c4e34"
  dark-purple: "#bea4dc"
  dark-blue: "#8fb8dd"
  dark-ochre: "#d6b376"
  dark-red: "#f29d9d"
  dark-amber: "#e8c68d"
  dark-amber-bg: "#3b3325"
typography:
  headline:
    fontFamily: "Fira, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "-.035em"
  title:
    fontFamily: "Fira, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "-.015em"
  body:
    fontFamily: "Fira, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Fira, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
  reading:
    fontFamily: "Fira, system-ui, sans-serif"
    fontSize: "29px"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-.04em"
rounded:
  small: "4px"
  tag: "5px"
  compact: "6px"
  control: "7px"
  notice: "8px"
  panel: "14px"
spacing:
  compact: "8px"
  control: "12px"
  small: "16px"
  panel-gap: "22px"
  panel-inset: "24px"
  page-inset: "38px"
components:
  button-primary:
    backgroundColor: "{colors.green}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "10px 15px"
    typography: "{typography.label}"
  button-primary-hover:
    backgroundColor: "{colors.green-hover}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 15px"
    typography: "{typography.label}"
  button-text:
    textColor: "{colors.muted}"
    padding: "5px 0"
  input:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  navigation-active:
    backgroundColor: "{colors.green-light}"
    textColor: "{colors.green}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
  tag:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.muted}"
    rounded: "{rounded.tag}"
    padding: "3px 8px"
  panel:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.panel}"
  metric-selected:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.text}"
    padding: "17px 14px 15px"
  coverage-day:
    backgroundColor: "{colors.soft}"
    rounded: "{rounded.control}"
    padding: "10px 8px"
---

# Design System: PulseCare

## Overview

**Creative North Star: "The Patient Field Atlas"**

A quiet, precise workspace for doctors reviewing remotely collected patient measurements in a university prototype. Mineral-white surfaces, forest selection and distinct signal colors make the patient’s recorded evidence the focus. Fira lends the interface a humanist, professional character without adding decorative display type.

The accepted direction is sleek and light by default, with an optional dark palette that preserves the same hierarchy. Thin borders and tonal surfaces organize the interface; chart annotations, actual coverage and plain-language availability states provide its detail. No generated raster imagery is shipped.

**Key Characteristics:**

- Mineral-white surfaces and forest-green actions.
- Flat panels, compact navigation and generous chart space.
- Distinct series colors, tabular readings and visible missing-data states.
- Responsive layouts and restrained, optional motion.

## Colors

The palette pairs mineral neutrals with a forest action color and muted instrument colors. Frontmatter names mirror the CSS custom properties in `assets/dashboard.css`; values are normative there and are not redefined in this prose.

### Primary

- **Forest** (`green`) identifies primary actions, active navigation, selection and reference readiness. `green-hover` strengthens primary-button hover.
- **Leaf tint** (`green-light`) backs selected navigation and recorded coverage; **mineral wash** (`wash`) gives the reference panel its quiet emphasis.

### Secondary

- **Optical violet** (`purple`) identifies heart rate.
- **Oxygen blue** (`blue`) identifies estimated blood oxygen.
- **Movement ochre** (`ochre`) identifies acceleration.
- **Temperature red** (`red`) identifies surface temperature and also supplies form-error text. Context and labels distinguish those uses.
- **Review amber** (`amber`, `amber-bg`) marks device alerts, missing hardware and departures requiring attention.

### Neutral

- **Mineral white** (`bg`) is the page ground; **paper** (`paper`) is the panel and header surface.
- **Sage paper** (`sidebar`) separates navigation; **soft mineral** (`soft`) backs quiet contextual rows and selected measurement cells.
- **Graphite** (`text`) carries primary text; **muted graphite** (`muted`) carries captions; **faint sage** (`faint`) is used for subdued icons and indicators.
- **Mineral rule** (`line`) separates adjacent regions without heavy outlines.

The `dark-` entries record the corresponding `[data-theme=dark]` overrides. The runtime uses the same semantic CSS variable names in either theme. A saved dark preference is restored; otherwise the interface starts in light mode.

**The Evidence Color Rule.** Series color identifies the measurement, while words explain availability and comparison state.

## Typography

**Display and body font:** locally hosted Fira Sans, registered as `Fira`, with `system-ui, sans-serif` fallbacks. Regular, medium and semibold files supply the interface. No separate display or monospace face is used.

The type is compact and humanist. Headings use medium weight rather than heavy contrast. Tabular numerals stabilize measurements, reference tables and device facts.

### Hierarchy

- **Headline:** the page title; reduces to (27px) on smaller screens.
- **Title:** section headings; the reference callout uses a larger (23px) treatment.
- **Body:** the base text role. Explanatory reference and clinician-facing copy uses (14px); dense rows and captions use (12px); form controls use (13px).
- **Label:** controls and small headings, with regular-weight variants for metadata.
- **Reading:** the dominant measurement; adjusts to (26px) at the compact-rail breakpoint and (27px) on phones.

## Layout

The shared shell combines a fixed left navigation rail, a thin header and a centered main region with a maximum width of (1500px). At full desktop size the rail is (222px), the header (78px), and page horizontal padding follows `page-inset`. Panels generally use `panel-inset` and `panel-gap`.

The implemented dashboard places a **horizontal four-cell metric strip** above its main time-series chart, with a reference-enrollment panel to the right. This is the accepted implementation; the earlier surface brief’s vertical selector is superseded by the shipped composition. Lower panels hold observations and hardware, followed by clinician review. Baseline and device views reuse the same shell. These are dashboard compositions, not requirements for every future screen.

- At (1600px) and above, the reference column and chart grow; chart height increases from (242px) to (285px).
- At (1220px) and below, the rail narrows to (194px), padding and column gaps compress, and metric labels can wrap.
- At (1050px) and below, navigation becomes an icon rail (78px).
- At (820px) and below, the principal columns stack; the reference callout briefly uses two internal columns.
- At (580px) and below, navigation becomes a fixed bottom bar (62px), metrics become a two-by-two grid, forms stack, and the chart is (210px) tall. The application reserves space for the bottom bar. Wide reference tables scroll horizontally.

## Elevation & Depth

Tonal layering and thin borders provide almost all depth. Main panels have no shadow. A restrained ambient shadow lifts temporary toast feedback; the active history-range option has a smaller inset-selection lift. There are no ornamental gradients or background imagery.

### Shadow Vocabulary

- **Toast:** `0 8px 28px rgba(30,55,40,.08)`.
- **Active history range:** `0 1px 3px rgba(20,40,25,.09)`.

Buttons transition background, text and border colors over (150ms). Navigation scrolls smoothly; reduced-motion preference removes smooth scrolling and transitions.

## Shapes

Rounded rectangular panels use the `panel` radius. Buttons, fields and navigation use the smaller `control` radius; tags and tooltips use the compact radii. Thin borders preserve separation between connected measurement cells. Circular identity discs and tiny connection or series dots remain subordinate to the written labels. Outline SVG icons share rounded strokes and restrained sizing, usually (19px), with smaller icons beside captions.

## Components

### Buttons

Primary actions use forest with paper text. Secondary actions use paper, a mineral border and graphite text. Text actions remove the box. Primary hover uses `green-hover`; text hover uses forest. The common visible keyboard outline is (2px) forest with a (4px) offset. Disabled buttons reduce opacity to (.5) and use the disabled cursor. The runtime has no separate secondary-button hover color.

### Inputs / Fields

Fields use the page ground, a mineral border and the control radius. Explicit labels remain above the controls, hints below, and errors use red text with an alert role. The clinician outcome select follows the same treatment. Enrollment asks for a patient name or reference; save-review is disabled until enrollment provides an identity.

### Navigation

Three destinations organize patient overview, patient baseline and device details. Active navigation uses leaf tint and forest text, with `aria-current` identifying the page. Hover uses the line tint. The compact rail retains accessible text while hiding it visually; the phone bar restores labels below icons.

### Chips / Tags

Quiet tags use a soft mineral background and muted text. Comparison tags add forest wash for within-reference state and amber for outside-reference state. Their wording carries meaning independently of color.

### Cards / Containers

Panels use paper, thin mineral borders and the panel radius. Headers provide concise titles and context. The reference callout uses mineral wash, while neutral context rows use soft mineral. The decorative reference symbol is illustrative geometry, not a plotted patient trace.

### Measurement strip and chart

Each metric cell presents a label, unit, value and measurement-quality note. Selected cells add a soft background and a thin forest underline. Left and Right arrows move between metric tabs. A shared plot changes to the selected series and one of three history windows: 15 minutes, 1 hour or 24 hours.

The SVG plot draws actual recorded values and breaks the path at null observations. Empty states explain why no reading is available. A personal reference band and dashed center appear only when a model exists. A time cursor exposes readings by pointer; a focusable chart supports Left/Right and Home/End to inspect valid readings. Keyboard instructions are available to assistive technology. The current tooltip reports time and measured value; it does not report a numeric reference comparison.

### Enrollment and recording coverage

The seven-day strip distinguishes empty, recorded and daily-qualified states with fill, numerals and check marks. The baseline page adds sampled-minute bars and a per-metric reference table. A day block indicates whether any metric has qualified that day; the table retains each metric’s independent readiness. Avoid presenting the decorative reference symbol as observed data.

### Clinician review and device details

The review form records an outcome and optional note for the current enrollment. Its displayed state is the latest browser-local review, not a longitudinal history. Hardware connectivity, measurement quality and reference readiness remain separate concepts. Detailed serial, memory and sensor information belongs in the device view; the overview shows the concise hardware summary.

## Do's and Don'ts

### Do:

- Do keep measured values, units and availability labels together.
- Do use the established series colors consistently in icons, lines and legends.
- Do preserve the visible focus outline and keyboard chart inspection.
- Do show patient identity and recording coverage before implying a reference is ready.
- Do keep chart nulls as gaps and unmeasured values as an em dash.

### Don't:

- Don’t add fabricated patient readings, historical curves or populated reference bands.
- Don’t use connectivity alone to imply valid measurements.
- Don’t present a personal-range departure as an automatic diagnosis.
- Don’t present a browser-local latest review as a shared clinical record or review history.
- Don’t replace the accepted light default with a dark-only interface.
