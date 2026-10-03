#!/usr/bin/env python3
"""Create a portable pg_dump backup and upload it to S3-compatible storage.

Required:
  DATABASE_URL
  SRGPC_S3_BUCKET or SRGPC_BACKUP_BUCKET
  SRGPC_S3_ACCESS_KEY
  SRGPC_S3_SECRET_KEY

Optional:
  SRGPC_S3_ENDPOINT
  SRGPC_S3_REGION
  SRGPC_BACKUP_PREFIX
  SRGPC_BACKUP_RETENTION_DAYS
"""
import datetime as dt
import os
import subprocess
import tempfile
from pathlib import Path

import boto3


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main():
    database_url = required("DATABASE_URL")
    bucket = os.environ.get("SRGPC_BACKUP_BUCKET", "").strip() or required("SRGPC_S3_BUCKET")
    access = required("SRGPC_S3_ACCESS_KEY")
    secret = required("SRGPC_S3_SECRET_KEY")
    endpoint = os.environ.get("SRGPC_S3_ENDPOINT", "").strip() or None
    region = os.environ.get("SRGPC_S3_REGION", "auto").strip() or "auto"
    prefix = os.environ.get("SRGPC_BACKUP_PREFIX", "postgres").strip().strip("/")
    retention_days = int(os.environ.get("SRGPC_BACKUP_RETENTION_DAYS", "30"))

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"srgpc_postgres_{timestamp}.dump"
    key = f"{prefix}/{filename}" if prefix else filename

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=region,
    )

    with tempfile.TemporaryDirectory(prefix="srgpc_backup_") as tmp:
        dump_path = Path(tmp) / filename
        subprocess.run(
            ["pg_dump", database_url, "--format=custom", "--no-owner", "--no-acl", "--file", str(dump_path)],
            check=True,
        )
        client.upload_file(
            str(dump_path),
            bucket,
            key,
            ExtraArgs={"ContentType": "application/octet-stream"},
        )

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retention_days)
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/" if prefix else ""):
        for item in page.get("Contents", []):
            modified = item.get("LastModified")
            if modified and modified < cutoff:
                client.delete_object(Bucket=bucket, Key=item["Key"])
    print(f"Backup uploaded: s3://{bucket}/{key}")


if __name__ == "__main__":
    main()
