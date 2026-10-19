# trading-bot – Paper-Trading & Backtesting (PAPER_ONLY)

Ereignisgetriebenes Trading-System für **simuliertes** Trading auf öffentlichen Binance-Spot-Marktdaten
und reproduzierbare Backtests. **Es gibt keinen Code, der echte Orders sendet**, und keinen Modus, der
das aktivieren könnte (siehe [Sicherheitsgrenzen](#sicherheitsgrenzen)).

- Architektur und Datenfluss: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Audit-Befunde: [docs/AUDIT.md](docs/AUDIT.md) · Fortschritt: [docs/PROGRESS.md](docs/PROGRESS.md) ·
  Roadmap: [docs/ROADMAP.md](docs/ROADMAP.md)

## Installation

Voraussetzung: Python ≥ 3.11 (getestet mit 3.11.2 unter Linux/aarch64).

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

Laufzeitabhängigkeiten: `requests` (REST-Kerzen), `websocket-client` (Live-Feed). Konfiguration
(`tomllib`), Persistenz (`sqlite3`) und Dezimalarithmetik kommen aus der Standardbibliothek.

## Schnellstart

```bash
venv/bin/python cli.py config                       # validierte Konfiguration + Modusübersicht
venv/bin/python cli.py fetch-data --profile backtest --symbol LUNCUSDT --days 5 --out data/LUNCUSDT_1m.csv
venv/bin/python cli.py backtest --csv data/LUNCUSDT_1m.csv
venv/bin/python cli.py paper --duration 30m         # Paper-Session auf Live-Daten (Ctrl+C stoppt sauber)
venv/bin/python cli.py status                       # letzter Lauf
venv/bin/python cli.py report --run-id <RUN_ID>     # Markdown/CSV/JSON-Report
```

`python main.py [Optionen]` entspricht `python cli.py paper [Optionen]`.

### Befehle

| Befehl | Zweck |
|---|---|
| `config` | Konfiguration laden, validieren und anzeigen (inkl. Config-Hash) |
| `fetch-data --symbol S --days N --out F` | geschlossene Kerzen über die öffentliche REST-API laden (paginiert, Rate-Limit-Behandlung, Lückenprüfung) |
| `backtest --csv F [--csv F2 ...]` | Backtest (nutzt automatisch Profil `backtest`) |
| `paper [--duration 24h] [--resume RUN_ID]` | Paper-Session; `--resume` setzt einen Lauf aus der Datenbank fort |
| `status [--run-id]` | Equity, PnL, Orders/Fills/Trades, Kill Switch, Health |
| `report [--run-id] [--out DIR]` | `report.md`, `report.json`, `trades.csv`, `round_trips.csv`, `equity.csv` |
| `runs` | Läufe auflisten |
| `reset-kill-switch --run-id` | gelatchten Drawdown-Kill-Switch manuell zurücksetzen |

Gemeinsame Optionen: `--profile NAME`, `--set section.key=value` (mehrfach, validiert), `--log-level`.

**Exit-Codes:** `0` ok · `1` Laufzeitfehler (Details in `logs/tradingbot.jsonl`) · `2` Konfigurations-/Bedienfehler ·
`3` Datenfehler (fehlende/ungültige Kerzen, unvollständiger Warmup).

## Konfiguration

Quellen (spätere überschreiben frühere): `config/default.toml` → `config/profiles/<profil>.toml` →
Umgebungsvariablen `TB_<SECTION>__<KEY>` (siehe [.env.example](.env.example)) → `--set`.
Unbekannte Sektionen/Schlüssel, falsche Typen, unplausible Werte und Schlüssel, die nach Zugangsdaten
aussehen, führen zu einem Fehler (Exit-Code 2) – es gibt keine stillen Fallbacks.

Profile: `default`/`paper` (Paper, `storage/sqlite/trading.db`), `dev` (Paper, `storage/sqlite/dev.db`),
`backtest` (Backtest, `storage/sqlite/backtest.db`). Kein Profil kann Live-Trading aktivieren.

| Schlüssel | Typ | Default | Wirkung |
|---|---|---|---|
| `run.mode` | `paper`\|`backtest` | `paper` | Betriebsart. Jeder andere Wert (z. B. `live`) wird abgelehnt. |
| `run.symbols` | Liste | `["LUNCUSDT"]` | Gehandelte Symbole; für jedes muss `[symbols.X]` existieren. |
| `run.timeframe` | str | `1m` | Kerzenintervall (`1m 3m 5m 15m 30m 1h 4h 1d`). |
| `run.database` | Pfad | `storage/sqlite/trading.db` | SQLite-Datei für Läufe, Orders, Fills, Trades, Equity. |
| `run.log_dir` | Pfad | `logs` | JSON-Log `tradingbot.jsonl` (rotierend, 5 × 10 MB). |
| `run.report_dir` | Pfad | `storage/reports` | Zielordner für Reports. |
| `run.seed` | int | `42` | Seed für zufällige Slippage (Reproduzierbarkeit). |
| `run.equity_snapshot_every_bars` | int | `1` | Equity-Snapshot alle N geschlossenen Kerzen. |
| `account.start_cash` | Dezimal | `1000` | Startkapital in Quote-Währung. |
| `account.quote_asset` | str | `USDT` | Nur informativ. |
| `costs.taker_fee_rate` | Dezimal | `0.001` | Gebühr je Fill (Market/Stop = Taker). |
| `costs.maker_fee_rate` | Dezimal | `0.001` | Reserviert; Limit-Orders sind nicht implementiert. |
| `costs.half_spread_bps` | Dezimal | `1` | Halber Spread in Basispunkten, verschlechtert jeden Fill. |
| `costs.slippage_bps` | Dezimal | `2` | Feste Slippage in bps. |
| `costs.random_slippage_bps` | Dezimal | `0` | Zusätzliche zufällige Slippage `U(0,1)·x` bps (Seed `run.seed`). |
| `execution.max_volume_participation` | Dezimal | `0.1` | Max. Anteil am Bar-Volumen je Bar (Teilfüllungen). Nur Backtest. |
| `execution.order_timeout_bars` | int | `3` | Entry-Restmengen werden danach storniert; Exits laufen weiter. |
| `risk.risk_per_trade_pct` | Dezimal | `1` | Risikobudget je Trade in % der Equity (Abstand Entry–Stop + Kosten). |
| `risk.max_position_notional_pct` | Dezimal | `25` | Max. Positionswert je Symbol in % der Equity. |
| `risk.max_total_exposure_pct` | Dezimal | `50` | Max. Brutto-Exposure aller Positionen in % der Equity. |
| `risk.max_open_positions` | int | `3` | Max. offene Positionen (inkl. ausstehender Entries). |
| `risk.max_daily_loss_pct` | Dezimal | `3` | Tagesverlust (UTC) → neue Entries bis zum nächsten UTC-Tag gesperrt. |
| `risk.max_drawdown_pct` | Dezimal | `20` | Drawdown vom Hoch → Kill Switch: alles schließen, Entries gesperrt bis manuellem Reset. |
| `risk.enable_shorts` | bool | `false` | Short-Entries erlauben (1× Sicherheitsleistung, keine Hebel). |
| `risk.allow_reversal` | bool | `false` | Gegensignal = Exit + neuer Entry (erfordert `enable_shorts`). |
| `strategy.name` | str | `ema_rsi` | Einzige implementierte Strategie. |
| `strategy.signal_mode` | `crossover`\|`state` | `crossover` | Entry nur bei frischer EMA-Kreuzung oder bei jedem Bar im Trendzustand. |
| `strategy.fast_period` / `slow_period` | int | `20` / `50` | EMA-Perioden (fast < slow). |
| `strategy.rsi_period` | int | `14` | RSI (Wilder). |
| `strategy.rsi_long_min` / `rsi_short_max` | float | `55` / `45` | RSI-Filter für Long-/Short-Entries. |
| `strategy.atr_period` / `atr_stop_multiple` | int / float | `14` / `2.0` | Stop = Close ∓ Multiple × ATR (Wilder). |
| `strategy.cooldown_bars` | int | `3` | Bars ohne neuen Entry nach einem Signal (Exits nie blockiert). |
| `market.ws_url` / `rest_url` | URL | Binance Spot | Nur `wss://` bzw. `https://` erlaubt; nur öffentliche Endpunkte. |
| `market.stale_after_seconds` | int | `30` | Ohne Nachricht länger als X s → Health `stale`, Ereignis `STALE_FEED`. |
| `market.warmup_candles` | int | `200` | Historische Kerzen vor Paper-Start (≥ Strategie-Warmup). |
| `market.reconnect_max_backoff_seconds` | int | `60` | Obergrenze für exponentiellen Backoff mit Jitter. |
| `market.queue_size` | int | `10000` | Größe der Trade-Queue (Backpressure). |
| `symbols.<S>.tick_size` `step_size` `min_qty` `min_notional` `max_qty` | Dezimal | je Symbol | Börsenregeln für Preisrundung, Mengen und Mindestnotional. **Vor Nutzung mit Binance `exchangeInfo` abgleichen.** |

## Paper-Trading-Ablauf

1. Konfiguration validieren, Modusübersicht ausgeben, Lauf mit Config-Hash in SQLite anlegen.
2. Warmup: `market.warmup_candles` **geschlossene** Kerzen per REST laden; ohne vollständigen Warmup kein Start (Exit 3).
3. Live-aggTrades (kombinierter Stream für alle Symbole) → Kerzen-Aggregation. Die erste, unvollständige Live-Kerze
   wird durch die geschlossene REST-Kerze ersetzt; Minuten ohne Trades werden zu Null-Volumen-Kerzen,
   außer nach einer Trade-ID-Lücke (dann `DATA_GAP`).
4. Bei jeder geschlossenen Kerze: Mark-to-Market, Kill-Switch-Prüfung, Strategie, Risiko-Prüfung, simulierte Order.
5. Orders werden **frühestens beim nächsten Trade nach Kerzenschluss** gefüllt (Spread, Slippage, Gebühr).
   Jede Position erhält einen reduce-only Schutz-Stop.
6. Alle 60 s Health-Status (Verbindung, Datenalter, Queue, Lücken, Equity) in die Datenbank.
7. Stopp (Ctrl+C, SIGTERM oder `--duration`): Feed schließen, Queue begrenzt abarbeiten, finaler Snapshot,
   Lauf `stopped`. Offene Positionen bleiben bestehen; `paper --resume RUN_ID` setzt fort
   (Ledger wird aus den gespeicherten Fills rekonstruiert; offene Orders werden storniert und Stops neu gesetzt).

## Backtesting

- Dieselben Komponenten wie im Paper-Modus (Strategie, Risiko, Broker, Ledger, Store).
- Signal auf Bar *t* → Fill frühestens zum Open von Bar *t+1*; Stops intrabar mit Gap-Behandlung (Fill zum
  schlechteren Open). Kein Lookahead, nur geschlossene Kerzen.
- Kosten immer aktiv; Teilfüllungen über `execution.max_volume_participation`.
- Datenqualität (Lücken, Duplikate, ungültige Kerzen) wird gemeldet und im Report als Warnung ausgegeben.
- Reproduzierbar: gleicher Input + gleiche Konfiguration (Hash) + Seed ⇒ gleiches Ergebnis (getestet).
- CSV-Format: `symbol,timeframe,open_time,close_time,open,high,low,close,volume` (ms UTC, `close_time` exklusiv).

## Reports und Kennzahlen

Definitionen stehen in [analytics/performance.py](analytics/performance.py). Kennzahlen basieren auf **Round-Trips**
(eine Position von Eröffnung bis Schließung, Teil-Schließungen gruppiert). Bei weniger als 30 Round-Trips, offenen
Positionen, Datenlücken oder ausgelöstem Kill Switch enthält der Report Warnungen. Profit Factor ohne Verlust-Trades
wird als `n/a` ausgegeben, nicht als ∞.

## Tests und Qualität

```bash
venv/bin/pytest                    # komplette Testsuite, ohne Netzwerkzugriff
venv/bin/ruff check . && venv/bin/ruff format --check .
```

## Sicherheitsgrenzen

- `PAPER_ONLY = True` ist im Code fest verankert ([core/config.py](core/config.py)); `run.mode` erlaubt nur
  `paper` und `backtest`.
- Es existiert kein Code für authentifizierte Endpunkte; ein Test schlägt fehl, sobald Order-Endpunkte oder
  Signatur-Code auftauchen (`tests/test_paper_and_cli.py::test_no_live_order_endpoint_anywhere`).
- Konfigurationsschlüssel, die nach Zugangsdaten aussehen, werden abgelehnt; Logs maskieren solche Muster.
- Jede Entry-Order läuft durch die Risiko-Engine; Ablehnungen werden mit Grund gespeichert (`events`, `signals`).

## Bekannte Einschränkungen

- Nur Market- und Stop-Market-Orders; **Limit-Orders sind nicht implementiert**.
- Paper-Modus: keine Orderbuchdaten → keine Liquiditätsbegrenzung, Spread ist ein konfigurierter Wert.
- Short-Simulation ist vereinfacht (1× Sicherheitsleistung, keine Leih-/Finanzierungskosten).
- Strategie-Zustand (Cooldown) wird bei `--resume` nicht wiederhergestellt; Indikatoren werden per Warmup neu aufgebaut.
- Exchange-Regeln in `config/default.toml` sind statisch und müssen manuell gepflegt werden.
- Kein News-, Liquiditäts-, Session- oder Higher-Timeframe-Filter aktiv.
- Ein 24-Stunden-Paper-Lauf wurde **noch nicht** durchgeführt (siehe [docs/PROGRESS.md](docs/PROGRESS.md)).
- Die Module der alten Pipelines liegen noch im Repository, werden aber nicht mehr verwendet (siehe
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#legacy-module)).

## Fehlerbehebung

| Symptom | Ursache / Lösung |
|---|---|
| `configuration error: ... PAPER_ONLY` | Unzulässiger Modus – nur `paper`/`backtest`. |
| `configuration error: Unknown key` | Tippfehler in TOML/`--set`/Umgebungsvariable. |
| `data error: ... warmup` | REST nicht erreichbar oder zu wenige Kerzen; Netzwerk prüfen, `market.warmup_candles` erhöhen. |
| `refusing to resume with different parameters` | `--resume` nur mit identischer Konfiguration (Config-Hash). |
| Report: „only N round trip(s)“ | Zu wenige Trades für belastbare Statistik – längeren Zeitraum testen. |
| Health `stale: true` | Keine Marktdaten seit `market.stale_after_seconds`; Feed verbindet automatisch neu. |
