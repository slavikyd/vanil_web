-- FnsID is not a unique document id in the Astral API: it is a 19-digit number
-- that arrives rounded to 64-bit float precision (always a multiple of 1024),
-- so different documents can share one value. A shift-close report and a
-- 220 RUB sale (kkt 0010431658059082, shift 64, check 7895) both came back as
-- '6555012373134679040'; the UNIQUE constraint made the ingestor's
-- ON CONFLICT DO NOTHING silently drop the sale.
--
-- The fiscal identity of a document is (fiscal_drive_number, shift_number,
-- check_number), which stays UNIQUE. fns_id is kept for lookups only.
ALTER TABLE ofd.receipts DROP CONSTRAINT IF EXISTS receipts_fns_id_key;
CREATE INDEX IF NOT EXISTS receipts_fns_id_idx ON ofd.receipts (fns_id);
