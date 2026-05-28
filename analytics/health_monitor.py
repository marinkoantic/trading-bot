import time

from core.state import SystemState

from utils.performance import PerformanceMonitor
from utils.logger import setup_logger


health_logger = setup_logger(
    "health_logger",
    "logs/system/health.log"
)


performance_monitor = PerformanceMonitor()


class HealthMonitor:

    def check_system_health(self):

        memory_usage = (
            performance_monitor.get_memory_usage_mb()
        )

        cpu_usage = (
            performance_monitor.get_cpu_usage()
        )

        health_logger.info(
            f"Memory={memory_usage:.2f}MB | "
            f"CPU={cpu_usage:.2f}% | "
            f"Ticks={SystemState.total_ticks_processed} | "
            f"Candles={SystemState.total_candles_processed}"
        )

        # MEMORY WARNING
        if memory_usage > 500:

            health_logger.warning(
                "High memory usage detected"
            )

        # CPU WARNING
        if cpu_usage > 90:

            health_logger.warning(
                "High CPU usage detected"
            )