# Audit – Phase 0 (2026-10-19)

Ausgangsstand: Branch `refactor/typed-event-architecture` @ `df79b7f`, plus lokale,
nicht committete Änderungen in `analytics/analytics_engine.py`, `analytics/equity_logger.py`,
`analytics/replay_engine.py`, `analytics/trade_logger.py`, `main.py` und die untracked Datei
`trade_ledger.py`. Diese Änderungen wurden nicht verworfen; die Arbeit läuft auf
`feature/paper-core-hardening`.

Legende: **[B]** bestätigt (reproduziert oder eindeutig im Code), **[V]** Vermutung, **[F]** offene Frage.

Die Spalte „Status“ bezieht sich auf den neuen Kern, den `main.py`/`cli.py` verwenden. Die Legacy-Module selbst
wurden nicht repariert, sondern stillgelegt (siehe [ARCHITECTURE.md](ARCHITECTURE.md#legacy-module)). Die P1-Befunde
sind im neuen Kern behoben und durch Tests abgesichert; Nachweise stehen in [PROGRESS.md](PROGRESS.md).

## Ausgeführte Prüfungen vor Änderungen

| Prüfung | Ergebnis |
|---|---|
| pytest-Tests | keine vorhanden (`test_bus.py`, `test_replay.py` sind Demo-Skripte ohne Assertions) |
| `python test_bus.py` (in Kopie) | läuft, schreibt aber in `storage/events/events.jsonl` |
| `python test_replay.py` (in Kopie) | **Fehler**: `ValueError: Unknown event type: SIGNAL` (`core/eventing/deserializer.py`) |
| Import aller Module | `market/market_stream.py` → `ModuleNotFoundError: market.reconnect_manager`; `market/reconnect-manager.py` nicht importierbar (Bindestrich im Dateinamen) |
| `ruff check` | 69 Meldungen (vor allem Import-Sortierung, ungenutzte Importe) |
| Reproduktionsskript (Kopie) | siehe P0-1 bis P0-5 |

## Tatsächlicher Datenfluss (vorher)

`main.py` startet **zwei parallele, sich überlagernde Pipelines**:

1. **Queue-Pipeline (Threads):** `market/websocket_client.on_message` → `tick_queue` →
   `candles/candle_engine.start_candle_engine` → `candle_queue` → *sowohl*
   `indicators/indicator_engine` *als auch* `strategy/strategy_engine` (konkurrierende Konsumenten!) →
   `strategy/signal_router` → `signal_queue` → `simulation/execution_engine` →
   `simulation/exchange_simulator` → `fill_queue` → `portfolio/portfolio.PortfolioEngine`.
2. **Event-Bus-Pipeline (synchron im WebSocket-Thread):** `on_message` → `event_bus.publish(TickEvent)` →
   `strategy/demo_strategy.DemoStrategy` (Signal bei *jedem* Tick) → `strategy/handlers/signal_handler` →
   `simulation/execution_simulator` (fest 1 000 000 Einheiten) → `portfolio/portfolio_manager.PortfolioManager`.

Beide Pipelines führen eigene, inkonsistente Portfolios.

## P0 – Sicherheit und kritische Fehler

| # | Befund | Ort | Status |
|---|---|---|---|
| P0-1 | **[B] PnL doppelt gezählt.** LONG-Eröffnung zieht Notional vom Cash ab, Schließen bucht `realized_pnl` *und* den vollen Exit-Notional zurück. Test: 100 @ 1.0 → 1.1 ergibt Balance 1020 statt 1010. Der gespeicherte Snapshot zeigt Balance 9790 bei Startkapital 1000 und realisiertem PnL −4,38. | `portfolio/portfolio.py` `open_position`/`close_position` | behoben (neues Ledger) |
| P0-2 | **[B] Equity falsch bei offener LONG-Position**: Equity = Cash + unrealisiert, Cash ist aber schon um das Notional reduziert → Equity fällt um das Notional. SHORT-Erlöse werden gar nicht gebucht. | `portfolio/account_state.py`, `portfolio/portfolio.py` | behoben |
| P0-3 | **[B] Keine Idempotenz**: derselbe Fill zweimal verarbeitet → Gebühr doppelt abgezogen (1.0 statt 0.5). | `portfolio/portfolio.py` `process_fill` | behoben (Fill-ID-Schutz) |
| P0-4 | **[B] Ausführungspfad stürzt ab**: `LiquidityEngine.calculate_fill_ratio` existiert nicht → `AttributeError`, Execution-Thread endet still (nur Log). | `simulation/exchange_simulator.py` | durch neuen Paper-Broker ersetzt |
| P0-5 | **[B] `PortfolioTickHandler` ruft `update_price` auf**, Methode heißt `update_market_price` → `AttributeError` bei jedem Tick. | `portfolio/handlers/portfolio_tick_handler.py` | Bus-Pipeline aus `main.py` entfernt |
| P0-6 | **[B] Unkontrollierte Orders**: `DemoStrategy` erzeugt bei *jedem* Tick ein LONG-Signal, `SignalEventHandler` handelt fest 1 000 000 Einheiten ohne Sizing, Exposure- oder Guthabenprüfung. | `strategy/demo_strategy.py`, `strategy/handlers/signal_handler.py` | aus Laufzeit entfernt |
| P0-7 | **[B] Konkurrierende Konsumenten auf `candle_queue`**: Indikator- und Strategie-Thread lesen dieselbe Queue; jede Kerze erreicht nur einen von beiden, Strategie kann veraltete Indikatoren nutzen. | `indicators/indicator_engine.py`, `strategy/strategy_engine.py` | behoben (synchrone Pipeline) |
| P0-8 | **[B] Kein PAPER_ONLY-Schutz**: kein Modus-Flag, keine Validierung. Echte Orderendpunkte sind *nicht* implementiert (kein API-Key, kein `/api/v3/order`), es ist also aktuell keine Live-Ausführung erreichbar. | `config/settings.py` | fail-closed Konfiguration ergänzt + Test |
| P0-9 | **[B] Risiko-Prüfungen umgehbar**: `RISK_PER_TRADE` wird als Notional-Anteil statt als Risikobudget genutzt; Mindestnotional *erhöht* stillschweigend die Größe; `MAX_ACCOUNT_EXPOSURE`, `MAX_DRAWDOWN_PERCENT` werden nirgends verwendet; kein Kill Switch. | `risk/position_sizer.py`, `config/settings.py` | behoben |
| P0-10 | **[B] Shutdown**: `graceful_shutdown` ruft `sys.exit` im Signal-Handler, alle Threads sind Daemons mit `while True` ohne Stop-Bedingung; offene Dateien/Zustand werden nicht kontrolliert gesichert. | `main.py` | behoben |
| P0-11 | **[B] Snapshot nicht atomar**: `json.dump` direkt auf Zieldatei; Absturz während des Schreibens zerstört den Zustand. Fehler beim Laden werden verschluckt (`except Exception: return None`) → stiller Neustart mit Default-Kapital. | `analytics/snapshot_manager.py` | ersetzt durch SQLite-Transaktionen |

## P1 – Kernlogik

| # | Befund | Ort |
|---|---|---|
| P1-1 | **[B] Zeitstempel-Einheiten gemischt**: Live-Kerzen in Sekunden, historische in Millisekunden (`open_time`/`close_time`). Binance-`close_time` ist `open + interval − 1 ms`. | `candles/candle_engine.py`, `data/historical_loader.py` |
| P1-2 | **[B] Letzte historische Kerze ist ungeschlossen**, wird aber mit `is_closed=True` gespeichert → Indikatoren auf unvollständigen Daten. | `data/historical_loader.py` |
| P1-3 | **[B] Hartcodierte Symbole**: `LUNCUSDT` in `websocket_client.py`, Default `BTCUSDT` in `CandleEngine`, `btcusdt` in `market_stream.py`; Trade-Log enthält deshalb `BTCUSDT`-Einträge mit LUNC-Preisen. | mehrere |
| P1-4 | **[B] RSI** nutzt einfache Mittelwerte der letzten 14 Deltas (Cutler-RSI) statt Wilder-Glättung; Grenzfall avg_gain=avg_loss=0 liefert 100 statt neutral. | `indicators/rsi.py` |
| P1-5 | **[B] EMA** ist korrekt (SMA-Seed), wird aber bei jeder Kerze über die gesamte, unbegrenzt wachsende Historie neu berechnet (Speicher wächst unbegrenzt). | `indicators/ema.py`, `candles/candle_store.py` |
| P1-6 | **[B] Strategie**: Kommentar sagt „crossover“, Code nutzt Zustandsbedingungen; Confidence fest 0.75; Signal-Zeitstempel = Wanduhr statt Kerzenzeit. | `strategy/strategy_engine.py` |
| P1-7 | **[B] Reversal-Fill**: Flip schließt mit der Fill-Menge der Gegenseite und eröffnet mit *derselben* Menge neu – Mengen von Schließen und Neueröffnen werden nicht getrennt. | `portfolio/portfolio.py` |
| P1-8 | **[B] Gebühren widersprüchlich**: `config/settings.py` 0.1 %, `simulation/fees.py` 0.02/0.04 %, `execution_simulator.py` 0.1 % fest. | mehrere |
| P1-9 | **[B] Slippage**: volle Kerzenspanne (`(high-low)/close`) wird zusätzlich zur Basis-Slippage addiert → unrealistisch hohe, nicht konfigurierbare Kosten; Zufallswerte ohne Seed. | `simulation/slippage.py`, `simulation/volatility_engine.py` |
| P1-10 | **[B] Latenz-Simulation blockiert** den Ausführungs-Thread per `time.sleep`. | `simulation/latency.py` |
| P1-11 | **[B] Exit eines SHORT** im Bus-Pfad füllt auf der Bid-Seite (müsste Ask sein). | `simulation/execution_simulator.py` |
| P1-12 | **[B] Trade-Log-Duplikate**: 663 Zeilen, viele identisch (alte Version loggte bei jedem Aufruf alle Trades; lokale Änderung dedupliziert über `symbol_timestamp`, was bei gleichem Zeitstempel kollidiert). | `analytics/analytics_engine.py`, `storage/jsonl/trades.jsonl` |
| P1-13 | **[B] Metriken inkonsistent**: Winrate einmal als Anteil, einmal in %; Profit Factor ohne Verluste 0 bzw. `inf`; Drawdown einmal absolut, einmal in %. | `analytics/metrics.py`, `analytics/performance_analyzer.py`, `analytics/statistics.py` |

## P2 – Infrastruktur

- **[B]** Keine Tests, kein `pyproject.toml`, kein Linter-Setup, keine README.
- **[B]** `requirements.txt` ohne Dev-Abhängigkeiten.
- **[B]** Logger ohne Rotation (`utils/logger.py`), `utils/rotation.py` ungenutzt; viel `print`-Debug-Ausgabe.
- **[B]** `ReplayRecorderMiddleware` öffnet bei jedem Event die Datei (I/O pro Tick); Deserializer kennt nur `MARKET_TICK`.
- **[B]** WebSocket-Reconnect: fester 5-s-Takt ohne Backoff/Jitter; `ReconnectManager` existiert, ist aber nicht importierbar.
- **[B]** Watchdog/Health-Monitor laufen in Endlosschleifen ohne Stop-Event.
- **[B]** Ungenutzte/leere Dateien: `core/config.py`, `core/eventing/execution.py`, `core/eventing/portfolio.py`, `core/eventing/strategy.py`, `simulation/oderbook.py`, `utils/timers.py`, `utils/dashboard.py` (referenziert nicht existierende Attribute), `execution/` (nur `__pycache__`), `storage/sqlite`, `storage/parquet` (leer).

## Offene Fragen

- **[F]** Soll die Strategie bei Gegen-Signal *umkehren* (Reverse) oder nur *schließen*? → sicherer Default: nur schließen, Reverse per Konfiguration (`allow_reversal`).
- **[F]** Sollen SHORTs auf Spot-Basis simuliert werden (Binance Spot erlaubt kein Short ohne Margin)? → Default: `enable_shorts=false`.
- **[F]** Sollen die alten Module (Queue- und Bus-Pipeline) gelöscht werden? → Nicht ohne Freigabe; sie sind jetzt als *Legacy* markiert und werden von `main.py` nicht mehr genutzt.
