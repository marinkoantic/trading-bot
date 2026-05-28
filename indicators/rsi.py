def calculate_rsi(prices, period=14):

    if len(prices) < period + 1:
        return None

    gains = []

    losses = []

    for i in range(1, len(prices)):

        delta = prices[i] - prices[i - 1]

        if delta >= 0:

            gains.append(delta)

            losses.append(0)

        else:

            gains.append(0)

            losses.append(abs(delta))

    avg_gain = sum(
        gains[-period:]
    ) / period

    avg_loss = sum(
        losses[-period:]
    ) / period

    if avg_loss == 0:

        return 100

    rs = avg_gain / avg_loss

    rsi = 100 - (
        100 / (1 + rs)
    )

    return rsi