# SiteSentry Desktop 1.2.0

## What's New

- Refreshed Light/Dark desktop interface with clearer status colors, sidebar navigation, KPI cards, and searchable/filterable monitor tables that preserve selection during refresh.
- Statistics views for monitor totals, individual outages, and error categories. Excel reports now include three sheets, filtered totals, printable layouts, and a reusable report template.
- Persistent failure categories distinguish rejected authentication, session verification, timeouts, server connectivity, local network availability, DNS/TLS, HTTP errors, assertions, and configuration errors.
- Email rules can exclude selected failure categories and group simultaneous Web/Auth Web/API failures into one list. The grouping window defaults to 15 seconds and can be set from 0 to 300 seconds.
- More reliable incident email ordering, duplicate prevention, per-recipient retries, and rule edits while alerts are queued. Daily summaries can omit currently DOWN monitors in excluded categories without changing the full report.
- Fixed intermittent UI stalls caused by Tk font/variable cleanup on background threads. Monitor Test Run now returns results through the UI queue and offers a separate diagnostics window.

## Downloads

- `Windows-x64.exe`: portable Windows executable. The ZIP contains the same executable; Python is not required.
- `macOS-arm64.dmg`: Apple Silicon Macs (M1 and later).
- `macOS-x64.dmg`: Intel Macs.
- `SHA256SUMS.txt`: SHA-256 checksums for all four packages.

## Installation and Upgrade

- Windows: run the EXE from a writable folder. This is a portable app, not an MSI/setup installer.
- macOS: open the matching DMG and copy SiteSentry Desktop.app to Applications.
- Quit the previous app before upgrading. Back up the app's `data` directory, including the database and Fernet key. The database schema upgrades automatically; keep the original key to read existing secrets.
- Packaged-app data is under `%APPDATA%\SiteSentry Desktop\data` on Windows or `~/Library/Application Support/SiteSentry Desktop/data` on macOS; source runs use the project's `data` directory.
- Existing email rules and recipients are preserved. Check Settings > Email schedules to choose excluded error categories and adjust the new grouping window; set it to 0 for immediate individual alerts.
- Legacy DOWN logs remain available and use the `unknown` error category when no category was recorded. Historical mail with unknown rule provenance is filtered conservatively if its category is excluded before sending begins.

## Notes

- Packages are not signed with a Windows publisher certificate or notarized with an Apple Developer certificate. Windows SmartScreen or macOS Gatekeeper may display a warning. Only proceed after verifying the download source and checksum.
- Email schedules run while the app is running (including in the tray), the machine is awake, and SMTP alerts are enabled.
- DOWN count means the number of DOWN log observations. Average downtime is calculated per incident; still-open incidents are measured through the report's observation time.
- Local network classification uses operating-system route evidence. Simultaneous monitor failures alone do not prove the monitoring machine is offline, and no third-party connectivity probe receives credentials or monitoring data.
- Authentication rejection requires HTTP 401 or an explicit visible rejection message in the login form. CAPTCHA/MFA or incomplete verification may instead be reported as session verification failures.
- Local validation passed 63 tests, including a native macOS UI scenario with 503 monitors. SMTP tests use mocks; this does not verify a particular SMTP provider or live credentials.
- To return to v1.1.0 after an upgrade, quit the app and restore the database and Fernet key backed up before upgrading; retain the newer backup separately.
