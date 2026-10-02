# LLM Docking

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Researchers configuring and presenting satellite docking experiments.

## Product Purpose

Run a configurable two-spacecraft docking simulation, observe its 3D motion,
and understand the controller and LLM decisions through a single dashboard.

## Operating Context

Local FastAPI application and a Kaggle notebook using two T4 GPUs for training.
The user selected a research simulator with a flight-operations dashboard.

## Capabilities and Constraints

Configurable spacecraft states and velocity limits; streamed telemetry; LangChain
tools; learned PPO advice; a shared capture gate bounded by 125 cm; training and
evaluation evidence under proofs/. Positions refer to docking ports in a local
coordinate frame. This is research software, without hardware certification.

## Evidence on Hand

Existing Python physics and controller tests and a small legacy PPO checkpoint.
No verified large-scale training results are supplied. Evidence must be generated
from actual runs with parameters, seeds, environment details, and artifact hashes.

## Product Principles

- Make the units and applied commands visible.
- Use readable functions and direct execution paths.
- Distinguish provider decisions, fallback behavior, and trained policy advice.
- Verify capture conditions independently of the planner.
