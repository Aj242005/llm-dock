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
  capture-confirmation:
    backgroundColor: "#162d27"
    textColor: "#d5f5e9"
    rounded: "{rounded.control}"
    padding: "18px 20px"
---

# Design System: Docking Lab

## Overview

**Creative North Star: "Flight-operations workbench"**

The user selected a flight-operations dashboard and then asked for a more
ambitious animated frontend. The graphite, mint, and blue identity remains;
larger typography and detailed schematic spacecraft give the relative flight
scene more presence. Configuration, capture, and guidance stay readable beside
the scene so researchers can compare commands with measured effects.

Motion follows backend measurements. A separate, labelled illustrative Earth
and static star field frame the spacecraft. Controls remain stable, native, and
task-focused; the only authored confirmation animation follows a server-verified
capture.

**Key Characteristics:**

- Explicit SI units
- Readable tool evidence
- Stable control surfaces
- Spatial telemetry
- Measured motion with a labelled illustrative backdrop

## Colors

Graphite surfaces use tonal layering and visible separators. Mint identifies
the controlled secondary, primary actions, and passed capture checks. Blue
identifies the target spacecraft and inspection links. Errors use a warm red
surface with readable light text. Status is always labelled in words.
The darker scene surface separates flight geometry from the workbench. Scene
labels use a pale blue-white; the capture confirmation uses a deep mint surface
with text tinted from the same hue.

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
are spaced apart when both docking ports converge.

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

The scene uses detailed schematic models whose origins are the docking ports;
one foreground scene unit is one metre. A separate shader Earth and static
stars remain labelled as an illustrative backdrop. Camera buttons expose chaser
tracking, both-port overview, and target-port views with aria-pressed states;
dragging enters manual orbit and a camera selection resumes tracking. Chaser
tracking frames both ports below 10m separation. Native checkboxes control the
trail, measured relative-velocity arrow, and capture envelopes. Exhaust points
opposite the applied force while the simulation is running. Positions and attitude
smooth toward measured telemetry with time-based exponential damping at 18 per
second; automatic camera movement uses 5 per second. There is no extrapolation.
Rendering pauses when the scene is offscreen or the document is hidden.

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
- Do preserve standard form semantics and reduced-motion behavior.
- Do keep schematic models and illustrative scenery explicitly labelled.
- Do reserve capture confirmation for the server's terminal docked event.
- Don't use animation to conceal latency or invent a physical outcome.
- Don't turn an observed success rate into an unqualified accuracy guarantee.
