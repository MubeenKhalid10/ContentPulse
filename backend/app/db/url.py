"""Accept the Postgres URLs hosted providers hand out.

Supabase, Neon, Render and Heroku-style dashboards give URLs such as
``postgres://user:pw@host:5432/db?sslmode=require``. SQLAlchemy's asyncpg
driver needs the ``postgresql+asyncpg`` scheme and rejects libpq's
``sslmode``, so this turns any of them into a working async URL plus the
matching connect arguments.
"""

import ssl
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}
# libpq-only options asyncpg doesn't understand.
_LIBPQ_ONLY = {
    "sslmode",
    "sslrootcert",
    "sslcert",
    "sslkey",
    "channel_binding",
    "pgbouncer",
    "connect_timeout",
}
_SSL_REQUIRED = {"require", "verify-ca", "verify-full"}
# Supabase's transaction pooler (and other PgBouncer transaction pools).
_TRANSACTION_POOL_PORTS = {6543}


def _escape_credentials(raw: str) -> str:
    """Percent-encode the user and password.

    Generated passwords often contain characters that are special in a URL
    (/ ? # @ :). Pasted unescaped, they cut the URL in the wrong place: part of
    the password ends up parsed as the host or port. The last "@" always
    separates the credentials from the host, so split there and encode both
    halves (decoding first, so an already-escaped password isn't escaped twice).
    """
    scheme, sep, rest = raw.partition("://")
    at = rest.rfind("@")
    if not sep or at == -1:
        return raw
    user, colon, password = rest[:at].partition(":")
    credentials = quote(unquote(user), safe="")
    if colon:
        credentials += ":" + quote(unquote(password), safe="")
    return f"{scheme}://{credentials}@{rest[at + 1 :]}"


def async_database_url(raw: str) -> tuple[str, dict[str, Any]]:
    """Return (sqlalchemy async URL, connect_args) for any Postgres URL."""
    parts = urlsplit(_escape_credentials(raw.strip()))
    try:
        port = parts.port
    except ValueError:
        # Never echo the URL: it holds the password.
        raise ValueError(
            "DATABASE_URL has an invalid host or port. Copy it again from your database "
            "provider (for Supabase: Connect > Session pooler)."
        ) from None
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"):
        scheme = "postgresql+asyncpg"

    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    sslmode = query.get("sslmode", "").lower()
    kept = {k: v for k, v in query.items() if k not in _LIBPQ_ONLY and k != "ssl"}
    ssl_param = query.get("ssl", "").lower()

    connect_args: dict[str, Any] = {}
    host = (parts.hostname or "").lower()
    remote = host not in _LOCAL_HOSTS and not host.endswith(".local")
    if sslmode in _SSL_REQUIRED or ssl_param in {"require", "true", "1"}:
        connect_args["ssl"] = _ssl_context(verify=sslmode.startswith("verify"))
    elif sslmode == "disable" or ssl_param in {"disable", "false", "0"}:
        connect_args["ssl"] = False
    elif remote and sslmode != "prefer":
        # Hosted databases expect TLS; local Docker Postgres doesn't offer it.
        connect_args["ssl"] = _ssl_context(verify=False)

    if port in _TRANSACTION_POOL_PORTS or query.get("pgbouncer") == "true":
        # Transaction pools can't keep prepared statements between queries.
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0

    url = urlunsplit((scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))
    return url, connect_args


def _ssl_context(*, verify: bool) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not verify:
        # Encrypted, but without CA pinning: providers' poolers often present
        # certificates the system store can't chain (sslmode=require semantics).
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context
