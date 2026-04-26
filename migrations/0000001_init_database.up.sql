Create EXTENSION if not EXISTS "uuid-ossp";


create table shops (
    id text primary key,
    phone_number text,
    address text -- TODO: do it the smarter way
    
);

CREATE TABLE categories (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name text NOT NULL UNIQUE
);

create table items (
	id uuid primary key default uuid_generate_v4(),
    name text,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    category uuid REFERENCES categories (id)
);



create table cashiers (
    id text PRIMARY key,
    full_name text,
    is_admin bool default False
);


create table orders (
    id uuid primary key default uuid_generate_v4(),
    created timestamp default now(),
    shop_id text REFERENCES shops (id),
    cashier_id text REFERENCES cashiers (id),
    comment text,
    order_for date NOT NULL DEFAULT CURRENT_DATE,
    address text
);

create table orders_items (
    order_id uuid references orders (id),
    item_id uuid REFERENCES items (id),
    quantity int,
    comment text,
    PRIMARY key(order_id, item_id)
);



create table shops_orders (
    shop_id text REFERENCES shops (id),
    order_id uuid REFERENCES orders (id),
    PRIMARY key(shop_id, order_id)
);


