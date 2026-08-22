"""boto3 is sync — every call here goes through asyncio.to_thread (CLAUDE.md §4: "Blocking
calls go through asyncio.to_thread ... never directly in the event loop").
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import boto3

from .config import get_settings


@lru_cache
def get_s3_client() -> Any:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=boto3.session.Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
        ),
    )


def _delete_prefix_sync(prefix: str) -> int:
    settings = get_settings()
    client = get_s3_client()
    deleted = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
        keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if not keys:
            continue
        client.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": keys})
        deleted += len(keys)
    return deleted


async def delete_prefix(prefix: str) -> int:
    """Deletes every object under `prefix`. Used by AS-05 (DELETE /me) to purge a user's audio
    prefix — CLAUDE.md §1.8, audio is never stored for personas but is for user recordings.
    """
    return await asyncio.to_thread(_delete_prefix_sync, prefix)
