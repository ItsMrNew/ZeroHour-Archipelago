"""Seeded trap allocation followed by weighted non-trap filler."""
from .mission_data import ITEM_NAME, POWER_TRAP_NAME

TRAP_NAMES = (POWER_TRAP_NAME, "Cash Theft", "Production Shutdown", "Sell Random Building")
FILLER_NAMES = (ITEM_NAME, "Supply Drop", "Reinforcements", "Production Surge", "Construction Boost")


def make_filler_pool(count, enabled, percentage, weights, rng, filler_weights=(50, 0, 0, 0, 0)):
    if len(filler_weights) == 3:  # legacy callers keep their previous distribution
        filler_weights = (*filler_weights, 0, 0)
    if count < 0:
        raise ValueError("Helpful items and unlocks exceed the available checks.")
    if not 0 <= percentage <= 100 or len(weights) != len(TRAP_NAMES) or any(
            not 0 <= weight <= 100 for weight in weights):
        raise ValueError("Trap percentage and weights must be between 0 and 100.")
    if len(filler_weights) != len(FILLER_NAMES) or any(type(w) is not int or not 0 <= w <= 100 for w in filler_weights):
        raise ValueError("Filler weights must be between 0 and 100.")
    if enabled and percentage and not any(weights):
        raise ValueError("Traps are enabled: give at least one trap a weight above zero, "
                         "or set the trap percentage to zero / disable traps.")
    trap_count = count * percentage // 100 if enabled else 0
    filler_count = count - trap_count
    if filler_count and not any(filler_weights):
        raise ValueError("Non-trap filler slots remain: give at least one helpful filler item a weight above zero.")
    choices = [(name, weight) for name, weight in zip(TRAP_NAMES, weights) if weight]
    traps = rng.choices([name for name, _ in choices],
                        weights=[weight for _, weight in choices], k=trap_count) if trap_count else []
    filler_choices = [(name, weight) for name, weight in zip(FILLER_NAMES, filler_weights) if weight]
    # Preserve the old RNG sequence when only Mission Reports are enabled.
    if not filler_count:
        filler = []
    elif len(filler_choices) == 1:
        filler = [filler_choices[0][0]] * filler_count
    else:
        filler = rng.choices([name for name, _ in filler_choices],
                             weights=[weight for _, weight in filler_choices], k=filler_count)
    return filler + traps
