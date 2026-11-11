# PC mandi publisher

Double-click **Start Mandi Publisher.vbs** to open the window and start refreshing.
The existing backend `.venv` needs `requests`, `python-dotenv`, `psycopg` and Tkinter.
Credentials are read from `AnnaData-Backend-main/.env`; they are never copied into
settings or logs. The application has no public server or tunnel.

The PC fetches official data.gov.in prices and writes state snapshots to the
existing Neon `mandi_cache`. The cloud chatbot reads this table on its fallback
path. No messages, farmer profiles, SMS sends, model requests or schema migrations
are involved in a refresh.

## Controls

- **Start service:** refresh immediately, then keep refreshing while the app runs.
- **Stop service:** cancel further work after the active bounded network operation.
  Already committed state snapshots remain available; an interrupted transaction rolls back.
- **Refresh now:** perform one refresh, even while the schedule is stopped.
- **Quit:** stop safely and exit. The window close button minimizes instead.
- States default to **West Bengal, Uttar Pradesh**; change the comma-separated list.
- Default interval is **180 minutes** because markets report throughout the day.
  Set **1440** for once daily. Sleep/offline time pauses effective refreshes; an
  overdue refresh runs after waking. The program does not stop Windows sleeping.

To launch on sign-in, place a shortcut to the VBS launcher in your Windows Startup
folder (`Win+R`, `shell:startup`). This is optional; no startup entry is installed automatically.
This is a resident user-session app, not a Windows service running before sign-in.

## Data rules

Only prices whose `arrival_date` equals today's date in India are published. Download
time must not turn an old price into a current price. Empty, invalid, incomplete or
changing paginated responses preserve the previous cache and show an error. Pagination
stops with an explicit error at the source's 10,000 offset boundary, rather than
silently publishing a partial state. Coverage is limited to reporting markets.

Each state is published in one transaction and read back for verification. Nothing
is ever deleted: this publisher only inserts, so a bad run cannot destroy the only
prices on file. Older commodity-specific entries are left in place as a fallback and
simply lose on age, because the reader ranks cached entries by date before
exactness and narrows a whole-state snapshot to the crop it was asked about. Only
cache data for selected states is touched. A failed state does not prevent other
states from refreshing; partial success is visible in the GUI.

The `.runtime` folder contains settings, last-cycle status and bounded logs. No
credentials are saved there. A localhost socket is reserved solely to prevent two
GUI instances; it never listens for connections. CLI `--once` is for diagnostics;
stop the GUI before using it.

## Checks and manual refresh

From the repository root:

```powershell
AnnaData-Backend-main/.venv/Scripts/python.exe local_mandi/app.py --dry-run
AnnaData-Backend-main/.venv/Scripts/python.exe local_mandi/app.py --once
AnnaData-Backend-main/.venv/Scripts/python.exe -m unittest discover -s local_mandi/tests
```

## Separate cloud investigation

`codex/mandi-cloud-cache` is reserved for cloud reader/network changes. The PC branch
does not deploy them. Follow-up work: cache-first reads, source-date-based freshness,
newest snapshot selection, broad vegetable queries, honest data-unavailable wording,
and monitoring/alarm handling for the failing cloud warm job. The old scheduled cloud
job remains unchanged; its successful future writes could replace a PC snapshot.
PC publishing restores available data but does not fix those independent behaviours.
