import os
import psutil


class PerformanceMonitor:

    def get_memory_usage_mb(self):

        process = psutil.Process(
            os.getpid()
        )

        memory_bytes = (
            process.memory_info().rss
        )

        return memory_bytes / 1024 / 1024

    def get_cpu_usage(self):

        return psutil.cpu_percent(interval=1)