from decimal import Decimal

from core.models import FillEvent

from simulation.fees import (
    calculate_fee
)

from simulation.slippage import (
    apply_slippage
)

from simulation.latency import (
    simulate_latency
)

from simulation.fills import (
    simulate_fill
)

from simulation.spread_engine import (
    SpreadEngine
)

from simulation.price_normalizer import (
    normalize_price
)

from candles.candle_engine import (
    candle_store
)

from simulation.volatility_engine import (
    VolatilityEngine
)

from simulation.liquidity_engine import (
    LiquidityEngine
)


spread_engine = SpreadEngine()

volatility_engine = (
    VolatilityEngine()
)

liquidity_engine = (
    LiquidityEngine()
)

class ExchangeSimulator:

    def execute_order(
        self,
        order
    ):

        latency_ms = (
            simulate_latency()
        )

        filled_quantity, is_partial = (
            simulate_fill(
                order.quantity
            )
        )
        
        fill_ratio = (
            liquidity_engine
            .calculate_fill_ratio(
                order.symbol,
                filled_quantity
            )
        )
        
        
        filled_quantity = float(
            Decimal(
                str(filled_quantity)
            ) * fill_ratio
        )
        
        if fill_ratio < Decimal("1.0"):
            is_partial = True
        
        
        candles = candle_store.get_candles(
            order.symbol,
            "1m"
        )
        
        volatility = 0
        
        if candles:
            
            latest_candle = candles[-1]
            
            volatility = (
                volatility_engine
                .calculate_volatility(
                    latest_candle
                )
            )

        # APPLY SPREAD
        execution_price = (
            spread_engine.apply_market_spread(
                order.symbol,
                order.side,
                order.price
            )
        )

        # APPLY SLIPPAGE
        execution_price = (
            apply_slippage(
                execution_price,
                order.side,
                volatility
            )
        )

        # NORMALIZE PRICE
        execution_price = (
            normalize_price(
                order.symbol,
                execution_price
            )
        )

        notional = (
            float(execution_price)
            * filled_quantity
        )

        fee = calculate_fee(
            notional
        )

        fill_event = FillEvent(

            order_id=order.order_id,
            
            symbol = order.symbol,
            
            side = order.side,

            filled_quantity=filled_quantity,

            fill_price=float(
                execution_price
            ),

            fee=fee,

            slippage=abs(
                float(execution_price)
                - order.price
            ),

            timestamp=order.timestamp,

            is_partial=is_partial
        )
        
        print("FILL EVENT CREATED")
        print(fill_event)

        return fill_event