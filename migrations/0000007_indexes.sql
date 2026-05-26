CREATE INDEX idx_orders_order_for ON orders(order_for DESC);
CREATE INDEX idx_orders_cashier_id ON orders(cashier_id);
CREATE INDEX idx_orders_shop_id ON orders(shop_id);
CREATE INDEX idx_orders_items_order_id ON orders_items(order_id);
