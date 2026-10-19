# Roadmap

Status: ✅ erledigt und getestet · 🟡 teilweise · ⬜ offen. Details zu jedem Lauf: [PROGRESS.md](PROGRESS.md).

## P0 – Sicherheit und kritische Fehler
- ✅ PAPER_ONLY als harte Grenze (Config, Test gegen Order-Endpunkte, Zugangsdaten abgelehnt)
- ✅ PnL-Doppelzählung, Equity-Fehler, doppelte Fills, abstürzender Ausführungspfad, konkurrierende Queues
- ✅ Risikoprüfung vor jeder simulierten Entry-Order, Kill Switch
- ✅ Kontrollierter Shutdown mit Zeitlimits
- ⬜ **Legacy-Module entfernen** (Liste in [ARCHITECTURE.md](ARCHITECTURE.md#legacy-module)) – wartet auf Freigabe
- ⬜ Alte Laufzeitdaten (`storage/snapshots/runtime_snapshot.json`, `storage/jsonl/trades.jsonl`, `storage/events/events.jsonl`)
  sind durch den PnL-Fehler verfälscht; nicht weiterverwenden, Archivierung oder Löschung durch den Nutzer

## P1 – Kernlogik
- ✅ UTC-ms-Zeitstempel, nur geschlossene Kerzen, Aggregation und Resampling
- ✅ EMA/RSI/ATR korrekt und getestet; Strategie mit explizitem Kreuzungs- oder Zustandsmodus
- ✅ Stop-basiertes Sizing, Order-Lebenszyklus, Gebühren, Slippage, Teilfüllungen, Reverse, Idempotenz
- ⬜ Exchange-Regeln automatisch aus `GET /api/v3/exchangeInfo` laden und gegen die Konfiguration prüfen
- ⬜ Strategie-Cooldown-Zustand beim Resume persistieren

## P2 – Infrastruktur
- ✅ Zentrale validierte Konfiguration mit Profilen, Umgebungs- und CLI-Overrides
- ✅ Strukturierte JSON-Logs mit Rotation und Redaktion
- ✅ SQLite-Persistenz, Migrationen, Wiederherstellung (getestet)
- ✅ Backtest mit derselben Kernlogik, reproduzierbar
- 🟡 Typprüfung: Typannotationen vorhanden, mypy noch nicht eingerichtet
- ⬜ Replay gespeicherter Live-Trades (Rohdaten-Aufzeichnung des Feeds) für deterministische Paper-Nachstellung

## P3 – Analyse und Bedienung
- ✅ Trade-Journal, Round-Trips, Equity-Verlauf, Kennzahlen, Markdown/CSV/JSON, Buy-and-Hold-Vergleich
- ✅ CLI: config, fetch-data, backtest, paper, status, report, runs, reset-kill-switch
- ⬜ **24-Stunden-Paper-Lauf** durchführen, protokollieren, auswerten (`python cli.py paper --duration 24h`)
- ⬜ Periodische Laufzusammenfassung im Log (z. B. stündlich)

## P4 – Erweiterungen (erst nach stabilem Basissystem)
- 🟡 Multi-Symbol: unterstützt und auf Isolation getestet; pro-Symbol-Strategieparameter und -Risikolimits fehlen
- ⬜ Limit-Orders (Maker-Gebühr) mit klaren Füllregeln
- ⬜ Higher-Timeframe-, Volumen-, Spread- und Session-Filter
- ⬜ Walk-forward-Analyse mit strikter Trennung von In-/Out-of-Sample
- ⬜ Optionale Alerts (Webhook/Telegram) als optionale Abhängigkeit
- ⬜ Optionales Dashboard (z. B. `rich`)
