alter table items add column if not exists pos integer;
alter table items add column if not exists tbl integer; -- TODO: unique constraint