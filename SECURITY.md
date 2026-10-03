# SRGPC production readiness

## Security
- Set a strong `SRGPC_SESSION_KEY` in Render. The application refuses to start in production without it.
- HTTPS-only secure sessions are enabled automatically on the Render URL.
- State-changing forms require a per-session CSRF token.
- Login, Google entry points, certificate generation, bulk generation, request submission and public verification are rate-limited.
- Security headers and request IDs are emitted on every response.
- Keep the master admin credentials only in Render environment variables.

## Shared rate limiting
The application uses `SRGPC_RATE_LIMIT_STORAGE_URI` when provided, then `REDIS_URL`, and otherwise falls back to in-process memory. For multiple web instances, configure a shared Redis-compatible store.

## Object storage
Use an S3-compatible bucket for generated PDFs and signatures: `SRGPC_S3_BUCKET`, `SRGPC_S3_ENDPOINT`, `SRGPC_S3_ACCESS_KEY`, `SRGPC_S3_SECRET_KEY`, `SRGPC_S3_REGION`, `SRGPC_S3_PREFIX`.

The app continues to work without object storage in local development.

## Database backups
`scripts/backup_postgres.py` creates a compressed PostgreSQL custom-format dump and uploads it to the configured S3-compatible backup bucket. Run it from a Render cron job on a daily schedule. The job requires the PostgreSQL client (`pg_dump`) and the backup environment variables documented in `.env.example`.

## Monitoring
Use Render service metrics/logs plus the public `/healthz` endpoint. Set the Render service health-check path to `/healthz`.

## Automated testing
The repository includes `pytest` smoke tests and GitHub Actions CI on every push/PR to `main`.
