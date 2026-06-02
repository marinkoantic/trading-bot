class ValuationEngine:

    def calculate_unrealized_pnl(
        self,
        entry_price,
        current_price,
        quantity,
        side
    ):

        if side == "LONG":

            return (
                (current_price - entry_price)
                * quantity
            )

        return (
            (entry_price - current_price)
            * quantity
        )