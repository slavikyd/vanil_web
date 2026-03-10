```mermaid
erDiagram
    shops {
        uuid id PK
        text phone_number
        text address
    }
    items {
        uuid id PK
        text name
        numeric price
        int ttl
        boolean active
    }
    warehouse {
        uuid id PK
        uuid item_id FK
        int quantity
        boolean is_expired
        timestamp supplied
        boolean is_imported_from_db
    }
    cashiers {
        text id PK
        text full_name
        boolean is_admin
    }
    orders {
        uuid id PK
        timestamp created
        uuid shop_id FK
        text cashier_id FK
        date order_for
    }
    orders_items {
        uuid order_id FK
        uuid item_id FK
        int quantity
    }
    shops_orders {
        uuid shop_id FK
        uuid order_id FK
    }

    shops ||--o{ orders : "placed at"
    shops ||--o{ shops_orders : "linked via"
    cashiers ||--o{ orders : "placed by"
    orders ||--o{ orders_items : "contains"
    orders ||--o{ shops_orders : "linked via"
    items ||--o{ warehouse : "stocked in"
    items ||--o{ orders_items : "included in"

```
