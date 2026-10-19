# Fortschritt

## Session 1 – 2026-10-19 (Branch `feature/paper-core-hardening`, nicht committet)

Ausgangsstand und alle Befunde: [AUDIT.md](AUDIT.md). Die lokalen, nicht committeten Änderungen des
Ausgangsbranches (`analytics/*`, `main.py`, `trade_ledger.py`) sind erhalten. `main.py` wurde ersetzt; die vorherige
Fassung enthielt nur Formatierungsänderungen gegenüber `df79b7f` und ist dort vollständig vorhanden.

### Erledigt

| Bereich | Dateien |
|---|---|
| Fail-closed Konfiguration, Profile, `.env.example` | `core/config.py`, `config/default.toml`, `config/profiles/*.toml`, `.env.example` |
| Domänenmodelle (Decimal, ms UTC) | `core/domain.py` |
| Indikatoren EMA, RSI (Wilder), ATR | `indicators/ema.py`, `indicators/rsi.py`, `indicators/atr.py` |
| Kerzen-Aggregation, Resampling, Validierung | `candles/aggregator.py` |
| EMA/RSI-Strategie (Kreuzung/Zustand, ATR-Stop, Cooldown) | `strategy/ema_rsi.py` |
| Risiko: Sizing, Limits, Kill Switch | `risk/risk_engine.py` |
| Paper-Broker | `simulation/paper_broker.py` |
| Ledger / Buchhaltung | `portfolio/ledger.py` |
| SQLite-Persistenz, Migrationen v1→v2, Recovery | `persistence/store.py` |
| Engine, Paper-Runner, Backtest | `app/engine.py`, `app/paper_runner.py`, `backtest/runner.py` |
| Kennzahlen & Reports (Round-Trips) | `analytics/performance.py` |
| Live-Feed, REST-Klines | `market/live_feed.py`, `data/klines.py` |
| Logging, CLI, Einstieg | `utils/log_setup.py`, `cli.py`, `main.py` |
| Tooling & Doku | `pyproject.toml`, `requirements-dev.txt`, `.gitignore`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/*` |
| Tests (101) | `tests/` |

### Tatsächlich ausgeführte Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `venv/bin/pytest` | **101 passed** (ohne Netzwerk) |
| `venv/bin/ruff check .` / `ruff format --check .` | sauber (Legacy-Module ausgenommen, siehe `pyproject.toml`) |
| `cli.py config --set run.mode=live` | Exit 2, Meldung „PAPER_ONLY“ |
| `cli.py fetch-data --symbol LUNCUSDT --days 5` | 7200 geschlossene 1m-Kerzen, 0 Lücken/Duplikate |
| `cli.py backtest --csv data/LUNCUSDT_1m.csv` (Defaults) | ok: −1,52 % vs. Buy & Hold −5,92 %, 59 Round-Trips, Win-Rate 10,2 %, PF 0,40, Gebühren 13,22 USDT, MaxDD 1,89 % |
| Buchhaltungs-Gegenprobe in SQLite | `1000 + Σ net_pnl` = Endequity; `Σ trade.fees` = `Σ fill.fee` (bis auf die 28. Stelle) |
| Migration einer echten v1-Datenbank | `storage/sqlite/backtest.db` beim zweiten Backtest auf v2 migriert |
| Paper-Session live, 150 s (`main.py --profile dev --duration 150s`) | Exit 0, Feed verbunden, 0 verworfene Trades, 0 Sequenzlücken, Status `stopped`; keine Signale im Zeitfenster. Aufgedeckt: Teilkerze beim Start und Leerminuten als Lücke → behoben (Backfill/Null-Volumen-Kerzen) |
| Paper-Session live, 200 s, nach dem Fix | Exit 0, 200 Warmup- + 3 Live-Kerzen, **0 Datenlücken-Ereignisse**, 0 Fehler im Log, Status `stopped`; keine Signale im Zeitfenster (also keine Orders) |

Die Strategie ist mit den Default-Parametern auf LUNCUSDT/1m in diesem Zeitraum **nicht profitabel**. Kosten
(Gebühren + Spread/Slippage ≈ 18,8 USDT) übersteigen den Bruttoertrag. Das ist ein Ergebnis, kein Fehler; es wurde
keine Parameteroptimierung vorgenommen.

### Offen / bekannte Risiken
- **24-Stunden-Paper-Lauf: nicht durchgeführt** → offen. In den beiden Live-Läufen (150 s, 200 s) wurde
  keine simulierte Order erzeugt; der Live-Orderpfad ist nur durch Tests mit gescriptetem Feed belegt.
- Legacy-Module noch im Repository (unbenutzt, siehe [ARCHITECTURE.md](ARCHITECTURE.md#legacy-module)); Löschung braucht Freigabe.
- Alte Laufzeitdaten unter `storage/snapshots`, `storage/jsonl`, `storage/events` sind durch den PnL-Fehler
  verfälscht (Snapshot zeigt Balance 9790 bei Start 1000) und werden nicht mehr gelesen.
- Exchange-Regeln (tick/step/minNotional) sind statisch in `config/default.toml` und nicht gegen `exchangeInfo` geprüft.
- Paper-Modus ohne Orderbuch: keine Liquiditätsbegrenzung, Spread als Konstante.
- Strategie-Cooldown wird beim Resume nicht wiederhergestellt.
- mypy nicht eingerichtet.
- Nichts committet (keine Freigabe erteilt).

### Nächste konkrete Schritte
1. Änderungen prüfen und committen (Vorschlag: ein Commit je Bereich oder ein Sammelcommit auf `feature/paper-core-hardening`).
2. Freigabe zum Entfernen der Legacy-Module, dann Ruff-Ausnahmen in `pyproject.toml` entfernen.
3. Exchange-Regeln aus `exchangeInfo` laden und validieren.
4. 24-h-Lauf: `venv/bin/python cli.py paper --duration 24h`, danach `cli.py report` und Auswertung hier dokumentieren.

### Fortsetzungsanweisung
> Lies `docs/PROGRESS.md`, `docs/ROADMAP.md` und `docs/ARCHITECTURE.md`. Führe `venv/bin/pytest` und
> `venv/bin/ruff check .` aus. Setze mit dem ersten offenen Punkt unter „Nächste konkrete Schritte“ fort.
