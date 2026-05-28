def render(state, portfolio, price):

    print(f"PRICE        : {price:.8f}")
    print(f"RSI          : {state.rsi:.2f}" if state.rsi else "RSI          : loading")
    print(f"EMA          : {state.ema:.8f}" if state.ema else "EMA          : loading")
    print(f"SIGNAL       : {state.signal}")

    print("\n--- PORTFOLIO ---")

    print(f"BALANCE      : {portfolio.balance:.4f}")
    print(f"EQUITY       : {portfolio.equity:.4f}")
    print(f"UNREAL PnL   : {portfolio.unrealized_pnl:.6f}")
    print(f"DRAWDOWN     : {portfolio.drawdown:.6f}")

    if portfolio.position:

        pos = portfolio.position

        print("\n--- POSITION ---")
        print(f"SIDE         : {pos.side}")
        print(f"ENTRY        : {pos.entry_price:.8f}")
        print(f"SL           : {pos.stop_loss:.8f}")
        print(f"TP           : {pos.take_profit:.8f}")