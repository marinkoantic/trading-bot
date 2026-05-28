def calculate_unrealized_pnl(
    entry_price,
    current_price,
    quantity,
    side
):

    if side == "LONG":

        return (
            current_price - entry_price
        ) * quantity

    return (
        entry_price - current_price
    ) * quantity


def calculate_realized_pnl(
    entry_price,
    exit_price,
    quantity,
    side
):

    if side == "LONG":

        return (
            exit_price - entry_price
        ) * quantity

    return (
        entry_price - exit_price
    ) * quantity