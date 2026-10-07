import ssl

from app.db.url import async_database_url


def test_local_url_is_untouched():
    url, args = async_database_url(
        "postgresql+asyncpg://contentpulse:contentpulse@localhost:5434/contentpulse"
    )
    assert url == "postgresql+asyncpg://contentpulse:contentpulse@localhost:5434/contentpulse"
    assert args == {}


def test_supabase_session_pooler_url():
    url, args = async_database_url(
        "postgresql://postgres.abcd:pw@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
        "?sslmode=require"
    )
    assert url.startswith("postgresql+asyncpg://postgres.abcd:pw@aws-0-eu-central-1")
    assert "sslmode" not in url
    assert isinstance(args["ssl"], ssl.SSLContext)
    assert "statement_cache_size" not in args


def test_transaction_pooler_disables_statement_cache():
    _, args = async_database_url("postgres://u:p@aws-0-x.pooler.supabase.com:6543/postgres")
    assert args["statement_cache_size"] == 0
    assert isinstance(args["ssl"], ssl.SSLContext)  # remote host: TLS by default


def test_sslmode_disable_and_other_params_kept():
    url, args = async_database_url("postgres://u:p@db.example.com/app?sslmode=disable&application_name=cp")
    assert args["ssl"] is False
    assert url.endswith("/app?application_name=cp")
