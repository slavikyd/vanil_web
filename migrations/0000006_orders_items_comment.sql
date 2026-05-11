-- Per line-item comment from cashier (stored at order time; not shown in admin UIs yet).
ALTER TABLE orders_items ADD COLUMN IF NOT EXISTS comment text;
