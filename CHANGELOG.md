# Changelog

## 0.2.0 – unreleased (Branch `feature/paper-core-hardening`)

### Sicherheit
- Fail-closed Konfiguration mit festem `PAPER_ONLY`; Modi nur `paper`/`backtest`; Zugangsdaten-Schlüssel abgelehnt.
- `main.py` startet nicht mehr die alten Pipelines (Demo-Strategie mit Order bei jedem Tick, feste 1 000 000 Einheiten).

### Behoben
- Doppelt gezählter PnL und falsche Equity bei offenen Positionen (neues Ledger, `portfolio/ledger.py`).
- Doppelte Fills wurden doppelt gebucht (Idempotenz über Fill-IDs in Ledger und SQLite).
- Absturz im Ausführungspfad (`calculate_fill_ratio`) und `update_price`-Fehler in der Bus-Pipeline (Pfade stillgelegt).
- Konkurrierende Konsumenten auf `candle_queue` (synchrone Pipeline).
- RSI nach Wilder statt einfacher Mittelwerte; flache Reihe liefert 50.
- Historische Warmup-Kerzen: ungeschlossene Kerze verworfen, einheitliche ms-Zeitstempel.

### Neu
- Stop-basiertes Position Sizing, Exposure-/Positionslimits, Tagesverlust- und Drawdown-Kill-Switch.
- Paper-Broker mit Order-Lebenszyklus, Teilfüllungen, Spread/Slippage (Seed), Schutz-Stops mit Gap-Behandlung.
- SQLite-Persistenz mit Migrationen, Wiederherstellung durch Fill-Replay.
- Backtest-Runner, Reports (Markdown/CSV/JSON), CLI, strukturiertes JSON-Logging mit Redaktion.
- WebSocket-Feed mit Backoff + Jitter, Sequenzlücken-Erkennung, REST-Backfill, Health-Status.
- 101 automatisierte Tests (ohne Netzwerk), Ruff-Konfiguration.
