# SiteSentry Desktop 1.1.0

## What's New

- Multiple independent email rules: one DOWN alert per incident and one recovery alert, recovery-only alerts, and scheduled daily dashboard summaries.
- Multiple recipients, custom subjects/messages, and a persistent SMTP retry queue with per-recipient tracking.
- Statistics by date/time range: DOWN checks, incidents, total downtime, average downtime, and open incidents.
- Excel statistics export with an incident detail sheet and durations that support more than 24 hours.
- Calendar and time selection for log filters and reports; log queries and exports run in the background.
- Language/framework and web server metadata for Web, Auth Web, API, and Excel import templates.

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
- Check Settings > Email schedules after upgrading. A default incident rule is created using existing SMTP recipients.

## Notes

- Packages are not signed with a Windows publisher certificate or notarized with an Apple Developer certificate. Windows SmartScreen or macOS Gatekeeper may display a warning. Only proceed after verifying the download source and checksum.
- Email schedules run while the app is running (including in the tray), the machine is awake, and SMTP alerts are enabled.
- DOWN count means the number of DOWN log observations. Average downtime is calculated per incident; still-open incidents are measured through the report's observation time.
