-- Day 1 Homework — Lakebase schema for the support app.
-- Run this once against your Lakebase (managed Postgres) instance.
-- Safe to re-run: everything is guarded with IF NOT EXISTS.

CREATE SCHEMA IF NOT EXISTS support;

CREATE TABLE IF NOT EXISTS support.tickets (
    ticket_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'in_progress', 'resolved')),
    -- Bonus: priority + category
    priority    TEXT        NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    category    TEXT,
    created_by  TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS support.ticket_messages (
    message_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id     BIGINT      NOT NULL
                  REFERENCES support.tickets (ticket_id) ON DELETE CASCADE,
    message_text  TEXT        NOT NULL,
    author        TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id
    ON support.ticket_messages (ticket_id);

CREATE INDEX IF NOT EXISTS idx_tickets_status
    ON support.tickets (status);
