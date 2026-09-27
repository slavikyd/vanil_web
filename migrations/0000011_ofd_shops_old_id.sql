ALTER TABLE ofd.shops ADD COLUMN old_id integer REFERENCES ofd.shops(id);
