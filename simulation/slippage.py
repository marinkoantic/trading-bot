import random


def apply_slippage(price, side):

    slippage_bps = random.uniform(
        1,
        5
    )

    slippage = (
        price *
        (slippage_bps / 10000)
    )

    if side == "BUY":

        return price + slippage

    return price - slippage