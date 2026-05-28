class SystemState:

    websocket_connected = False

    last_tick_timestamp = None

    last_candle_timestamp = None

    total_ticks_processed = 0

    total_candles_processed = 0

    total_signals_generated = 0

    total_orders_created = 0

    total_fills_created = 0