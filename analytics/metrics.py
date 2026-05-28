class MetricsCalculator:

    def calculate_winrate(self, trades):

        if not trades:
            return 0

        wins = [
            t for t in trades
            if t.realized_pnl > 0
        ]

        return len(wins) / len(trades)

    def calculate_total_pnl(self, trades):

        return sum(
            t.realized_pnl
            for t in trades
        )

    def calculate_average_pnl(self, trades):

        if not trades:
            return 0

        total = self.calculate_total_pnl(trades)

        return total / len(trades)

    def calculate_profit_factor(self, trades):

        gross_profit = sum(
            t.realized_pnl
            for t in trades
            if t.realized_pnl > 0
        )

        gross_loss = abs(sum(
            t.realized_pnl
            for t in trades
            if t.realized_pnl < 0
        ))

        if gross_loss == 0:
            return 0

        return gross_profit / gross_loss