import random
import time


def simulate_latency():

    latency_ms = random.randint(
        50,
        300
    )

    time.sleep(
        latency_ms / 1000
    )

    return latency_ms