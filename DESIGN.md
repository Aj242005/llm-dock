---
name: Docking Lab
description: A research flight-operations workbench
colors:
  primary: "#8fd9c4"
  primary-text: "#112820"
  secondary-text: "#d3e0e6"
  target: "#90b9e9"
  background: "#10191f"
  surface: "#162128"
  scene: "#070e16"
  scene-text: "#c6d5e2"
  border: "#30424d"
  text: "#e5edf1"
  muted: "#a0b3be"
  danger: "#ffb1a5"
typography:
  headline:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "clamp(30px, 3vw, 46px)"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  headline-mobile:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "31px"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "15px"
    fontWeight: 500
  body:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "11px"
    fontWeight: 400
  instrument:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "26px"
    fontWeight: 400
    letterSpacing: "-0.025em"
rounded:
  control: "5px"
  tag: "4px"
  segment: "3px"
spacing:
  compact: "8px"
  group: "14px"
  panel: "20px"
  page: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-text}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.secondary-text}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
  camera-segment:
    backgroundColor: "transparent"
    textColor: "{colors.scene-text}"
    rounded: "{rounded.segment}"
    padding: "8px 11px"
  camera-segment-selected:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-text}"
    rounded: "{rounded.segment}"
    padding: "8px 11px"
  grid-spacing-select:
    backgroundColor: "#101b22"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "6px 8px"
  capture-confirmation:
    backgroundColor: "#162d27"
    textColor: "#d5f5e9"
    rounded: "{rounded.control}"
    padding: "18px 20px"
---

# Design System: Docking Lab

## Overview

**Creative North Star: "Flight-operations workbench"**

The research flight-operations dashboard keeps its graphite, mint, and blue
identity. Larger typography, a NASA ISS primary, and a concept chaser give the
relative flight scene more presence. Configuration, capture, and guidance stay
readable beside the scene so researchers can compare commands with measured
effects. The shared XYZ grid makes the same local port coordinates visible from
centimetres to hundreds of metres per division.

Motion follows backend measurements and continues while provider guidance is
pending. Planning status and decision snapshot provenance remain readable beside
current telemetry. A separate, labelled illustrative Earth and static star field
frame the spacecraft. Controls remain stable, native, and task-focused; the only
authored confirmation animation follows a server-verified capture.

**Key Characteristics:**

- Explicit SI units
- Readable tool evidence
- Stable control surfaces
- Spatial telemetry
- Shared XYZ coordinates at true metre scale
- Measured motion with a labelled illustrative backdrop
- Visible guidance state and decision snapshot provenance

## Colors

Graphite surfaces use tonal layering and visible separators. Mint identifies
the controlled secondary, primary actions, and passed capture checks. Blue
identifies the target spacecraft and inspection links. Errors use a warm red
surface with readable light text. Status is always labelled in words.
The darker scene surface separates flight geometry from the workbench. Scene
labels use a pale blue-white; the capture confirmation uses a deep mint surface
with text tinted from the same hue.

The XYZ legend and scene arrows reuse the established warm red for X, mint for
Y, and blue for Z. Axis letters accompany color in both the legend and the 3D
labels. The NASA model status uses target blue when ready and the established
danger tone for a loading failure; its message states the fallback in words.

## Typography

Self-hosted IBM Plex Sans carries headings, forms, explanations, and
measurements, with 400, 500, 600, and 700 weights and the bundled OFL licence.
Tabular numerals align telemetry. Code and exported JSON use the browser
monospace stack. The main heading scales with the viewport and becomes 31px
through 700px. Instrument values use 26px by default, 20px in the two-column
layout, and 24px on mobile. Chart labels remain 11px at the actual rendered
width; the empty trace message is ordinary 12px HTML.

## Layout

Desktop uses 260px configuration, a flexible flight view, and a 290px guidance
log within an 1800px maximum page width. At 1500px and above, side columns expand
to 280px and 310px. At 1150px and below, configuration remains 260px wide and
the log spans both columns beneath the flight view. At 700px and below, the
layout stacks and all fields remain available. From 701px, configuration is
sticky with an independently scrolling field area and mission actions outside
that area. The desktop field area has a 360px minimum height and a maximum of
the viewport height minus 430px. Primary spacecraft parameters begin closed and
secondary parameters open. On initial mobile load all configuration disclosures
begin closed, and expanded fields occupy a scroll area capped at 430px. Mobile
actions remain in document flow in two columns; the API reference link stays
visible. The canvas resizes with its container and has an explicit height:
570px by default, 640px from 1500px, and 430px through 700px. Camera controls,
captions, and projected spacecraft labels occupy separate scene regions; labels
are spaced apart when both docking ports converge and their boxes are clamped
inside the canvas with 10px padding. The grid controls occupy a wrapping row
below the existing scene overlays, with 12px vertical and 18px horizontal gaps
and 12px by 20px padding. The model status occupies its own full-width line.

## Elevation & Depth

Panels use flat surfaces and one-pixel separators. Depth comes from the 3D
scene. The terminal capture confirmation is the sole raised UI surface, with an
offset, soft shadow (0 10px 28px #0005). Controls communicate hover and focus
through color and outlines.

## Shapes

Controls and scene labels have 5px corners; compact state tags have 4px corners
and camera segments have 3px corners. Workspace
surfaces use square corners. Standard inputs, selects, checkboxes, and details
retain native behavior.

## Components

Primary and secondary buttons use identical spacing and icon weight. Lucide
icons use consistent strokes. Configuration has a short introductory instruction
and native disclosures, fields, and checkboxes. Guidance entries show source and
simulation time, short explanations, and expandable tool/alternative details.
Empty and error states explain the next action. Keyboard focus is a two-pixel
mint outline with a three-pixel offset.

### Guidance and continuous motion

The existing explanation panel and flat decision log carry planning activity;
the scene and instruments continue receiving measured telemetry through SSE.
The planning status uses "Planning in background" with "coasting under safety
limits", "following the active maneuver", or "local braking", according to the
telemetry event. Before the first maneuver, the spacecraft coast under the local
safety envelope. Subsequent requests continue the active maneuver. Only one
provider request runs at a time, and configured motion and actuator limits are
enforced every physics step. Abort or sensor loss immediately selects local
braking. The playback help states "Motion continues while Gemini plans."

Received decisions report their snapshot age in simulated seconds. Expandable
"Tools & learned advice" evidence includes the request snapshot time, age, and
applied flag. The latest rationale, learned assessment, alternatives, and tool
results come from that decision's request-time snapshot; they can describe an
earlier measured state than the current instruments. A proposal outside its age
budget or with a changed fault context is labelled "discarded" and "Discarded
proposal"; the status states "Delayed response discarded · local braking".
Accepted proposals are checked against current limits, with safety adjustments
appended as "Applied limits". Stop and terminal events end the session and its
pending request; the command status then reads "Last applied command · session
ended". These states reuse the incumbent typography, separators, and labelled
status treatment.

### Spacecraft and local frame

One foreground scene unit is one metre, and each spacecraft origin is its docking
port. The primary loads NASA's stationary ISS GLB from the local model directory.
The locally optimized asset preserves named nodes and mesh geometry, with meshopt
compression, deduplication, and 1024px WebP textures. Its PMA-2 forward tip is
translated to the local port origin and rotated 90 degrees about Y. The secondary
is a dimensional concept chaser with a faceted shell, protective port ring, fins,
solar panels, and sensor details. The caption identifies the NASA ISS, concept
chaser, and illustrative Earth separately. Loading failure leaves the schematic
target visible and a status message explains that reloading retries the asset.

Physics X maps to scene X, physics Y to negative scene Z, and physics Z to scene
Y. Positions, velocities, force arrows, and attitudes use this shared basis. The
grid remains fixed in the local coordinate frame while the shared camera orbits
the grid and spacecraft together. A separate shader Earth and static stars remain
labelled as an illustrative backdrop.

### Camera view selector

Four native buttons expose "Track chaser", "ISS + chaser", "Full ISS", and
"Target port" with aria-pressed states; "ISS + chaser" is initially selected.
Dragging enters manual orbit, scroll zooms, and selecting a camera resumes
automatic placement. Reset refits the selected mode. Chaser tracking shows the
chaser at its true model scale and frames both ports below 10m separation or after
capture. Target port is a close inspection view of the primary port.

The overview includes the ISS bounds and the chaser's physical extent; Full ISS
fits the station alone. Both derive distance from a bounding sphere and the
smaller horizontal or vertical camera half field of view, with 1.25 padding.
Automatic placement refits after model loading and container resize. This keeps
physical scale consistent as the canvas aspect ratio changes.

### Shared XYZ grid and overlays

The native 3D grid checkbox starts checked. The spacing select offers Auto,
1cm, 10cm, 1m, 10m, and 100m per division. Auto uses 10cm below 1m port
separation, 1m below 10m, 10m through 200m, and 100m above 200m. Three
intersecting XY, XZ, and YZ planes meet at the primary docking-port origin, with
20 divisions spanning ten spacings in either direction. Translucent grid lines,
colored positive-axis arrows, and constant screen-size labels establish the
frame; a live output states the actual spacing and drag gesture. Changing
spacing replaces and disposes the previous grid geometry and label textures.

Native checkboxes also control the measured flight trail, relative-velocity arrow,
and capture envelopes. Exhaust points opposite the applied force while the
simulation is running. Positions and attitude smooth toward measured telemetry
with time-based exponential damping at 18 per second; automatic camera movement
uses 5 per second. There is no extrapolation. Rendering pauses when the scene is
offscreen or the document is hidden.

### Initial placement fields

Native XYZ position inputs show metres and accept arbitrary decimal steps. The
default primary port is [0, 0, 0] and the secondary is [100, 0, 0], giving 100m
initial separation. The inclusive permitted distance is 2cm to 1km, measured as
the Euclidean separation between the two configured ports. Starting range min.
and max. can narrow that band. A native validity message reports the allowed
band and measured separation, with a 1e-9 metre endpoint tolerance. Invalid
fields reveal their disclosure before browser focus. Seeded randomization places
the secondary relative to the configured primary within the selected band, and
the scene caption reports playback speed and actual initial separation.

Buttons transition background and border color over 160ms; fields transition
border color over the same duration. Reduced motion removes these transitions
and the confirmation animation, and snaps spacecraft and automatic camera
updates to their targets.

The capture gate displays four labelled checks. Only the terminal server docked
event reveals the capture confirmation: a 550ms clipped reveal with exponential
ease-out and the measured final range and relative speed. A completed capture is
also labelled "Captured" and "Docking complete", with the capture action disabled
and the last applied command labelled as a finished session. Starting or resetting
a session clears the confirmation. The responsive trace derives its viewBox
from its rendered width so text retains its size.

## Do's and Don'ts

- Do show units beside every configurable quantity and measurement.
- Do keep numerical telemetry tied to backend events.
- Do label the deterministic planner and provider fallback honestly.
- Do keep planning activity, current telemetry, and request-time reasoning separately labelled.
- Do expose decision snapshot age and whether a returned proposal was applied or discarded.
- Do preserve standard form semantics and reduced-motion behavior.
- Do identify the NASA ISS, concept chaser, fallback target, and illustrative scenery explicitly.
- Do share the local coordinate frame and true metre scale across models, grid, and telemetry.
- Do keep grid spacing and visibility in native labelled controls, with the current division size visible.
- Do fit full-scene cameras from physical bounds and the limiting field of view when the canvas resizes.
- Do reserve capture confirmation for the server's terminal docked event.
- Don't use animation to conceal latency or invent a physical outcome.
- Don't turn an observed success rate into an unqualified accuracy guarantee.
