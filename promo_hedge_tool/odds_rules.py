from __future__ import annotations


def decimal_to_american(decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        raise ValueError("Decimal odds must be greater than 1.0")
    if decimal_odds >= 2.0:
        return (decimal_odds - 1.0) * 100.0
    return -100.0 / (decimal_odds - 1.0)


def meets_american_requirement(decimal_odds: float, operator: str | None, requirement: float | None) -> bool:
    if operator is None or requirement is None:
        return True
    american_odds = decimal_to_american(decimal_odds)
    if operator == ">=":
        return american_odds >= requirement
    if operator == "<=":
        return american_odds <= requirement
    raise ValueError("operator must be >= or <=")