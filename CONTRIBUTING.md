# Beitragen

1. **PAPER_ONLY bleibt unverhandelbar.** Keine authentifizierten Endpunkte, keine API-Schlüssel, kein Live-Modus.
   `tests/test_paper_and_cli.py::test_no_live_order_endpoint_anywhere` muss grün bleiben.
2. Vor jedem Commit:
   ```bash
   venv/bin/ruff format . && venv/bin/ruff check . && venv/bin/pytest
   ```
3. Jeder behobene Fehler bekommt einen Regressionstest. Tests dürfen kein Netzwerk benötigen
   (Fakes für Feed/REST wie in `tests/test_paper_and_cli.py`).
4. Geld, Preise und Mengen in der Buchhaltung sind `Decimal`; Zeitstempel sind Millisekunden UTC.
5. Neue Konfigurationsschlüssel: Dataclass in `core/config.py`, Validierung in `_validate`,
   Default in `config/default.toml`, Tabelle in `README.md`.
6. Schemaänderungen nur als neuer Eintrag in `persistence/store.py::MIGRATIONS` (append-only).
7. `docs/PROGRESS.md` und ggf. `docs/ARCHITECTURE.md` mit dem Code aktualisieren.
