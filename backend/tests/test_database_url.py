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


def test_cors_origins_accept_plain_or_json(monkeypatch):
    from app.core.config import Settings

    for raw in ("https://cp.vercel.app/", '["https://cp.vercel.app"]'):
        monkeypatch.setenv("CORS_ORIGINS", raw)
        assert Settings(_env_file=None).cors_origins == ["https://cp.vercel.app"]


def test_password_with_url_special_characters():
    from sqlalchemy.engine import make_url

    password = "a/b?c#d@e:f+g!"
    raw = f"postgresql://postgres.abcd:{password}@aws-0-eu.pooler.supabase.com:5432/postgres"
    url, args = async_database_url(raw)
    parsed = make_url(url)
    assert parsed.password == password
    assert parsed.host == "aws-0-eu.pooler.supabase.com" and parsed.port == 5432
    assert parsed.database == "postgres"
    assert isinstance(args["ssl"], ssl.SSLContext)


def test_already_escaped_password_is_not_escaped_twice():
    from sqlalchemy.engine import make_url

    url, _ = async_database_url("postgresql://u:a%2Fb@db.example.com:5432/app")
    assert make_url(url).password == "a/b"


def test_bad_port_error_hides_the_url():
    import pytest

    with pytest.raises(ValueError) as exc:
        async_database_url("postgresql://u:secret@host:notaport/db")
    assert "secret" not in str(exc.value)
