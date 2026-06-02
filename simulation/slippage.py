from decimal import Decimal


BASE_SLIPPAGE = Decimal(
    "0.0007"
)


def apply_slippage(
    price,
    side,
    volatility=Decimal("0")
):

    price = Decimal(
        str(price)
    )

    slippage_percent = (
        BASE_SLIPPAGE
        + volatility
    )

    slippage_amount = (
        price * slippage_percent
    )

    # BUY = WORSE PRICE
    if side == "BUY":

        return (
            price + slippage_amount
        )

    # SELL = WORSE PRICE
    return (
        price - slippage_amount
    )