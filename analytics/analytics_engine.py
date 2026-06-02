import time

from analytics.trade_logger import TradeLogger
from analytics.metrics import MetricsCalculator
from analytics.statistics import StatisticsTracker

from utils.logger import setup_logger

from portfolio.account_state import (
    account_state
)


analytics_logger = setup_logger(
    "analytics_logger",
    "logs/analytics/analytics.log"
)


trade_logger = TradeLogger()

metrics_calculator = MetricsCalculator()

statistics_tracker = StatisticsTracker()


class AnalyticsEngine:

    def process_portfolio(self, portfolio_engine):

        trades = portfolio_engine.trade_history

        total_pnl = (
            metrics_calculator.calculate_total_pnl(
                trades
            )
        )

        winrate = (
            metrics_calculator.calculate_winrate(
                trades
            )
        )

        avg_pnl = (
            metrics_calculator.calculate_average_pnl(
                trades
            )
        )

        profit_factor = (
            metrics_calculator.calculate_profit_factor(
                trades
            )
        )

        statistics_tracker.update_equity(
            account_state.balance
        )

        analytics_logger.info(
            f"Balance={account_state.balance} | "
            f"TotalPnL={total_pnl} | "
            f"Winrate={winrate} | "
            f"AvgPnL={avg_pnl} | "
            f"ProfitFactor={profit_factor} | "
            f"MaxDrawdown={statistics_tracker.max_drawdown}"
        )

        # LOG CLOSED TRADES
        for trade in trades:

            trade_logger.log_trade(trade)