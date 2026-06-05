import signal
import sys
import threading
import time

from market.websocket_client import start_websocket

from core.eventing.bootstrap import (
    setup_eventing,
)

from data.historical_loader import (
    HistoricalLoader
)

from candles.candle_engine import start_candle_engine

from indicators.indicator_engine import (
    start_indicator_engine
)

from strategy.strategy_engine import (
    start_strategy_engine
)

from simulation.execution_engine import (
    start_execution_engine
)

from portfolio.portfolio import (
    start_portfolio_engine
)

from analytics.health_monitor import (
    HealthMonitor
)

from analytics.watchdog import (
    Watchdog
)

from utils.logger import setup_logger


from config.settings import (
    TRADING_SYMBOL,
    TRADING_TIMEFRAME,
    HISTORICAL_CANDLE_LIMIT
)

from utils.thread_wrapper import (
    safe_thread_runner
)


system_logger = setup_logger(
    "system_logger",
    "logs/system/system.log"
)


shutdown_event = threading.Event()


health_monitor = HealthMonitor()

watchdog = Watchdog()

historical_loader = HistoricalLoader()


def run_health_monitor():

    while not shutdown_event.is_set():

        health_monitor.check_system_health()

        time.sleep(60)


def run_watchdog():

    watchdog.monitor()


def graceful_shutdown(signum, frame):

    system_logger.info(
        "Graceful shutdown initiated"
    )

    shutdown_event.set()

    sys.exit(0)
    
    

def start_thread(
    target,
    name
):

    thread = threading.Thread(

        target=safe_thread_runner(
            target,
            name
        ),

        daemon=True,

        name=name
    )

    thread.start()

    system_logger.info(
        f"{name} started"
    )

    return thread


def warmup_historical_data():

    system_logger.info(
        "Loading historical candles..."
    )

    loaded = (
        historical_loader.load_historical_candles(
            symbol= TRADING_SYMBOL,
            interval= TRADING_TIMEFRAME,
            limit= HISTORICAL_CANDLE_LIMIT
        )
    )

    system_logger.info(
        f"{loaded} historical candles loaded"
    )





def main():

    setup_eventing()
    
    signal.signal(
        signal.SIGINT,
        graceful_shutdown
    )

    signal.signal(
        signal.SIGTERM,
        graceful_shutdown
    )

    system_logger.info(
        "Starting Trading System"
    )
    
    # Historical WARMUP
    warmup_historical_data()

    threads = [

        start_thread(
            start_websocket,
            "WebsocketThread"
        ),

        start_thread(
            start_candle_engine,
            "CandleEngineThread"
        ),

        start_thread(
            start_indicator_engine,
            "IndicatorEngineThread"
        ),

        start_thread(
            start_strategy_engine,
            "StrategyEngineThread"
        ),

        start_thread(
            start_execution_engine,
            "ExecutionEngineThread"
        ),

        start_thread(
            start_portfolio_engine,
            "PortfolioEngineThread"
        ),

        start_thread(
            run_health_monitor,
            "HealthMonitorThread"
        ),

        start_thread(
            run_watchdog,
            "WatchdogThread"
        )
    ]

    system_logger.info(
        "All system threads started"
    )

    while not shutdown_event.is_set():

        time.sleep(1)


if __name__ == "__main__":

    main()