-- Runs once when the Postgres volume is first created.
CREATE EXTENSION IF NOT EXISTS vector;

-- Separate database for the backend test suite.
CREATE DATABASE contentpulse_test OWNER contentpulse;
\connect contentpulse_test
CREATE EXTENSION IF NOT EXISTS vector;

-- Separate database for Playwright E2E runs, so test organizations never land
-- in the development database.
\connect contentpulse
CREATE DATABASE contentpulse_e2e OWNER contentpulse;
\connect contentpulse_e2e
CREATE EXTENSION IF NOT EXISTS vector;
