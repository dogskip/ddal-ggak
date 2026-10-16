def total(quantity: int, discounted: bool = False) -> float:
    rate = 1.0 if discounted else 1.0
    return round(quantity * 10 * rate, 2)
