"""Operator commands for the shared provider cache.

    python -m app.sources.cache_admin status          # rows and bytes per provider
    python -m app.sources.cache_admin purge --source reddit
    python -m app.sources.cache_admin purge --all

Purging honors a provider's deletion request at once (the hourly housekeeping
also removes providers that are no longer allowed to be stored). Prints
counts only: never keys, bodies or credentials.
"""

import argparse
import asyncio

from sqlalchemy import text


async def status() -> None:
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        rows = await db.execute(
            text(
                "SELECT source, count(*), coalesce(sum(size_bytes), 0), "
                "count(*) FILTER (WHERE expires_at > now()) "
                "FROM provider_cache GROUP BY source ORDER BY source"
            )
        )
        print(f"{'source':<20}{'rows':>8}{'fresh':>8}{'bytes':>12}")
        for source, count, size, fresh in rows:
            print(f"{source:<20}{count:>8}{fresh:>8}{size:>12}")


async def purge(source: str | None) -> None:
    from app.sources.provider_cache import store

    print(f"Deleted {await store.purge(source)} stored response(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p = sub.add_parser("purge")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--source")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.command == "status":
        asyncio.run(status())
    else:
        asyncio.run(purge(None if args.all else args.source))


if __name__ == "__main__":
    main()
