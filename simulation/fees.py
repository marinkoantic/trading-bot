MAKER_FEE = 0.0002

TAKER_FEE = 0.0004


def calculate_fee(notional, is_maker=False):

    fee_rate = MAKER_FEE if is_maker else TAKER_FEE

    return notional * fee_rate