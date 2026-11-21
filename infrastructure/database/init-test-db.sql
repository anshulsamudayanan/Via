-- Runs once when the Compose Postgres volume is first created.
-- Creates the database used by integration tests (VIA_TEST_DATABASE_URL); tests reset it freely.
CREATE DATABASE via_test OWNER via;
