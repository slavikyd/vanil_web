CREATE TABLE ofd.ingest_runs (
  id             bigserial PRIMARY KEY,
  mode           text NOT NULL,             -- 'all' | 'recent'
  started_at     timestamptz NOT NULL,
  finished_at    timestamptz NOT NULL DEFAULT now(),
  pages_walked   int NOT NULL DEFAULT 0,
  documents_seen int NOT NULL DEFAULT 0,
  receipts_new   int NOT NULL DEFAULT 0,
  error          text
);

CREATE INDEX ON ofd.ingest_runs (mode, started_at);

DROP TABLE IF EXISTS ofd.load_log;
