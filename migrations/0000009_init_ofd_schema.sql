CREATE SCHEMA IF NOT EXISTS ofd;

-- Reference tables (you fill these; the OFD doesn't give you this)
CREATE TABLE ofd.shops (
  id          serial PRIMARY KEY,
  name        text NOT NULL,          -- "Кондитерская на Московской"
  address     text,
  city        text,
  opened_on   date,
  timezone    text DEFAULT 'Europe/Moscow'
);

CREATE TABLE ofd.registers (
  kkt_reg_id          text PRIMARY KEY,         -- "0010409242060390"
  shop_id             int REFERENCES ofd.shops(id),
  fiscal_drive_number text,                     -- changes when the FN is replaced
  active_from         date,
  active_to           date
);

CREATE TABLE ofd.items (
  id            serial PRIMARY KEY,
  name_raw      text UNIQUE NOT NULL,   -- exact receipt text
  name_clean    text,                   -- "Эклер малина-фисташка"
  category      text,                   -- cake / pastry / cookie / drink / frozen / candles
  subcategory   text,                   -- eclair, trifle, mousse dessert, whole cake…
  sold_by       text,                   -- 'piece' | 'kg'
  unit_weight_g int,                    -- parsed from "90г", "750г/шт"
  is_marked     boolean DEFAULT false   -- Честный знак goods
);

CREATE TABLE ofd.cashiers (
  id         serial PRIMARY KEY,
  name_raw   text UNIQUE NOT NULL,      -- "Продавец-кассир Мацак Светлана Анатольевна"
  name_clean text,                      -- normalized, title-cased, prefix stripped
  role       text
);

-- Core fact tables
CREATE TABLE ofd.receipts (
  id                  bigserial PRIMARY KEY,
  fns_id              text UNIQUE,                 -- FnsID / fdId
  kkt_reg_id          text NOT NULL REFERENCES ofd.registers,
  fiscal_drive_number text NOT NULL,
  shift_number        int  NOT NULL,
  check_number        int  NOT NULL,
  fiscal_sign         bigint NOT NULL,
  document_type       smallint NOT NULL,           -- 3 = receipt
  operation_type      smallint NOT NULL,           -- 1 sale, 2 sale refund, 3 expense, 4 expense refund
  issued_at           timestamptz NOT NULL,
  date                date NOT NULL,               -- local calendar day
  cashier_id          int REFERENCES ofd.cashiers,
  taxation_type       smallint,
  is_marked           boolean,
  total_kop           bigint NOT NULL,             -- keep kopecks as integers
  cash_kop            bigint NOT NULL DEFAULT 0,
  ecash_kop           bigint NOT NULL DEFAULT 0,
  prepaid_kop         bigint NOT NULL DEFAULT 0,
  credit_kop          bigint NOT NULL DEFAULT 0,
  provision_kop       bigint NOT NULL DEFAULT 0,
  vat                 jsonb,                       -- {"ndsNo":130000,"nds22":0,...}
  fns_code            int,
  fns_errors          jsonb,                       -- error/warning arrays, usually empty
  item_count          int,                         -- lines on the receipt
  raw                 jsonb NOT NULL,              -- full original document
  loaded_at           timestamptz DEFAULT now(),
  UNIQUE (fiscal_drive_number, shift_number, check_number)
);

CREATE TABLE ofd.receipt_items (
  receipt_id  bigint REFERENCES ofd.receipts ON DELETE CASCADE,
  line_no     smallint,
  item_id     int REFERENCES ofd.items,
  quantity    numeric(10,3) NOT NULL,     -- 0.732 kg or 2 pcs
  price_kop   bigint NOT NULL,            -- unit price (per piece or per kg)
  amount_kop  bigint NOT NULL,            -- round(quantity * price), computed on load
  PRIMARY KEY (receipt_id, line_no)
);

CREATE INDEX ON ofd.receipts (issued_at);
CREATE INDEX ON ofd.receipts (kkt_reg_id, issued_at);
CREATE INDEX ON ofd.receipts (date);
CREATE INDEX ON ofd.receipt_items (item_id);