class StatisticsTracker:

    def __init__(self):

        self.equity_curve = []

        self.max_equity = 0

        self.max_drawdown = 0

    def update_equity(self, equity):

        self.equity_curve.append(equity)

        if equity > self.max_equity:
            self.max_equity = equity

        drawdown = (
            self.max_equity - equity
        )

        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown