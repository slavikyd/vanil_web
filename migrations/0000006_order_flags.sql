alter table orders add column disabled boolean not null default false;
alter table orders add column completed boolean not null default false;