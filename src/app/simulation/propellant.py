"""Equivalent-thruster propellant accounting shared by the runner and training."""

import numpy as np

from app.simulation.dynamics import Command

G0_MPS2 = 9.80665


def mass_flow_kgps(
    command,
    specific_impulse_s=220,
    rcs_specific_impulse_s=60,
    rcs_lever_arm_m=0.75,
    capacity_kg=25,
    legacy_rate=None,
):
    """Mass flow = thrust / (Isp * g0); opposing RCS pairs use |torque| / arm.

    The engine uses equivalent resultant thrust. RCS torque demand is summed
    per axis. This is an actuator model, not calibrated spacecraft hardware.
    """
    thrust = float(np.linalg.norm(command.force_n))
    rcs_thrust = float(np.sum(np.abs(command.torque_nm))) / rcs_lever_arm_m
    if legacy_rate is not None:
        return capacity_kg * legacy_rate / 100 * (thrust + rcs_thrust) / 50
    return thrust / (G0_MPS2 * specific_impulse_s) + rcs_thrust / (G0_MPS2 * rcs_specific_impulse_s)


def apply_propellant(
    state,
    command,
    dt,
    capacity_kg=25,
    specific_impulse_s=220,
    rcs_specific_impulse_s=60,
    rcs_lever_arm_m=0.75,
    legacy_rate=None,
):
    """Limit commands to available propellant and subtract their actual impulse cost.

    Call before propagation. Inertia follows mass at a fixed assumed geometry.
    Returns the applied command, consumed kilograms, and kilograms per second.
    """
    flow = mass_flow_kgps(
        command,
        specific_impulse_s,
        rcs_specific_impulse_s,
        rcs_lever_arm_m,
        capacity_kg,
        legacy_rate,
    )
    available = capacity_kg * state.fuel_pct / 100
    consumed = min(available, flow * dt)
    if flow * dt > available:
        scale = available / (flow * dt)
        command = Command(force_n=command.force_n * scale, torque_nm=command.torque_nm * scale)
    old_mass = state.mass_kg
    state.mass_kg -= consumed
    state.inertia = state.inertia * (state.mass_kg / old_mass)
    state.fuel_pct = max(0, (available - consumed) / capacity_kg * 100)
    return command, consumed, consumed / dt
