create Table shops_groups (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name text NOT NULL UNIQUE
)

alter table shops add column if not exists shop_group uuid REFERENCES shops_groups(id);