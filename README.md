# SRGPC Certificate Management System v6

A Flask-based college certificate platform with student and admin portals, certificate requests, QR verification, signatures, bulk generation, audit logs, staff roles and certificate lifecycle management.

## Windows quick start

1. Extract the ZIP.
2. Double-click `RUN.bat`.
3. The script creates a local virtual environment and installs the listed requirements.
4. Open `http://127.0.0.1:5000`.

### Admin login

For deployment, set the admin credentials using the `SRGPC_ADMIN_USERNAME` and `SRGPC_ADMIN_PASSWORD` environment variables. Do not store credentials in this repository.

## v6 reliability fixes

### Certificate engine
- Rebuilt all eight PDF templates around one fixed A4-landscape safe layout.
- Final PDFs and the browser's live preview use the exact same ReportLab renderer.
- Long student names and achievement text automatically shrink to a safe size.
- Long words are broken safely instead of escaping the page.
- Signature lines and signature images stay inside a dedicated signature band.
- Footer metadata has separate fixed zones for roll number, academic year/type and certificate ID.
- QR verification now uses a dedicated 98pt panel with a 74pt scan area and quiet zone.
- QR and footer are kept clear of the signatures and outer certificate border.
- Midnight certificates place signatures on white signature pads for readability.
- Skyline uses a separate content center so text never crosses the left side panel.

### Admin UI fixes
- Quick Actions render as real clickable cards.
- Certificate Archive action buttons and revocation form no longer overlap.
- Student + academic-year text in tables now stacks cleanly.
- Bulk CSV page has a proper two-column layout, file drop area and readable example block.
- Analytics/audit rows no longer run actor names and roles together.
- Static CSS/JS cache busting is enabled so visual fixes appear immediately after updating.

## Main features

### Student portal
- Student registration and login
- Account identity tied to name + roll number
- Certificate request workflow
- Request status history
- In-app notifications
- Certificate wallet / achievement portfolio
- Search and download issued certificates
- Only certificates matching the student's registered roll number are downloadable

### Admin portal
- Separate pages for each function; no scroll-based tab switching
- Manual certificate generation
- Exact PDF live preview
- Certificate request queue
- Eight certificate templates
- Helvetica / Times / Courier font choices
- SRGPC college logo
- Teacher and principal signature upload or drawing
- Live signature preview in Signature Studio
- QR code on every certificate (configurable)
- Public no-login certificate verification page
- Admin hash verification
- Duplicate certificate protection
- Certificate statuses: Valid / Revoked / Reissued
- Reissue flow with replacement certificate ID
- Certificate archive search
- Bulk CSV generation with ZIP output
- Academic-year support
- Analytics dashboard
- Audit log
- Staff accounts with Manager / Verifier roles

## Verification
Each certificate gets:

- Unique SRGPC certificate ID
- Cryptographic payload hash
- Stored PDF SHA-256 checksum
- Large QR code linking to the public verification page

Public verification:
`/verify/<CERTIFICATE_ID>`

API verification:
`/api/verify/<CERTIFICATE_ID>`

## CSV bulk format

Required columns:

`Name, Roll Number, Activity, Position`

Optional columns:

`Certificate Type, Academic Year, Template, Font Family`

The Bulk Generation page contains a ready-to-copy example.

## Deployment

The repository includes `Procfile` and `render.yaml` as a starting point for Render-style deployment.

Set these environment variables for a public deployment:

- `SRGPC_SESSION_KEY`
- `SRGPC_PUBLIC_BASE_URL`
- `SRGPC_ADMIN_USERNAME`
- `SRGPC_ADMIN_PASSWORD`

### Production storage note

The app uses SQLite and stores generated PDFs/signatures on the local filesystem. A production college deployment should use persistent storage or migrate the database/file storage to managed services before relying on the system for long-term records.


## v6.1 UI improvements
- The Generate Certificate page now uses an instant in-page SVG preview instead of an embedded PDF viewer. Typing updates the preview immediately without Adobe Acrobat/iframe reloads.
- The supplied transparent SRGPC logo is used as the official certificate logo.
- Burgundy Honor was redesigned with a restrained wine/ivory/gold layout.
- Template defaults, font defaults, QR toggle, and academic-year settings have a cleaner admin layout.
- The live preview uses a fixed A4-landscape viewBox and safe footer/signature zones.
