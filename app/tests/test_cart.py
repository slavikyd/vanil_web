"""
Test cart operations with mocked DB and Redis.
"""

from app.tests.fixtures.constants import ADMIN_ID, ITEM_ID
from unittest.mock import AsyncMock, MagicMock, patch


async def test_add_item_to_cart(client, mock_db_pool, mock_redis):
    """Test adding an item to cart successfully."""
    pool, conn = mock_db_pool

    conn.fetchrow.return_value = {
        "id": ADMIN_ID,
        "name": "Admin",
        "is_admin": True,
    }

    resp_login = await client.post("/login", data={"cashier_id": ADMIN_ID})
    assert resp_login.status_code in (200, 302)

    response = await client.post(
        "/add-to-cart",
        data={"item_id": str(ITEM_ID), "quantity": 2},
        follow_redirects=False,
    )

    assert response.status_code == 302


async def test_add_item_to_cart_no_session(client, mock_redis):
    """Test adding to cart without session redirects to home."""
    response = await client.post(
        "/add-to-cart",
        data={"item_id": str(ITEM_ID), "quantity": 1},
        follow_redirects=False,
    )

    assert response.status_code == 302


async def test_remove_from_cart(client, mock_db_pool, mock_redis):
    """Test removing an item from cart."""
    pool, conn = mock_db_pool

    conn.fetchrow.return_value = {
        "id": ADMIN_ID,
        "name": "Admin",
        "is_admin": True,
    }

    await client.post("/login", data={"cashier_id": ADMIN_ID})

    response = await client.post(
        "/remove-from-cart",
        data={"item_id": str(ITEM_ID)},
        follow_redirects=False,
    )

    assert response.status_code == 302


async def test_place_order_empty_cart(client, mock_db_pool, mock_redis):
    """Test placing order with empty cart fails with 400."""
    pool, conn = mock_db_pool

    conn.fetchrow.return_value = {
        "id": ADMIN_ID,
        "name": "Admin",
        "is_admin": True,
    }

    mock_redis.hgetall.return_value = {}

    from app.services.order_service import EmptyCartError
    conn.execute.side_effect = EmptyCartError("Cart is empty")

    await client.post("/login", data={"cashier_id": ADMIN_ID})

    response = await client.post(
        "/place_order",
        data={"order_for": "2026-01-17"},
        follow_redirects=False,
    )

    assert response.status_code == 400


# TODO Figure smth out with that

# async def test_place_order_success(client, mock_db_pool, mock_redis):
#     """Test placing order with items in cart."""
#     pool, conn = mock_db_pool

#     mock_redis.hgetall.return_value = {str(ITEM_ID): 2}
#     mock_redis.delete.return_value = None

#     conn.fetchrow.return_value = {
#         "id": ADMIN_ID, 
#         "name": "Admin", 
#         "is_admin": True
#     }
    
#     conn.fetch.return_value = [
#         {"id": ITEM_ID, "name": "Test Item", "price": 100},
#     ]
    
#     conn.execute.return_value = None
    
#     await client.post("/login", data={"cashier_id": ADMIN_ID})
    

    
#     from unittest.mock import patch, AsyncMock
    
#     mock_session = {
#         "cashier_id": ADMIN_ID,
#         "session_id": "some-session-id",
#         "tg_id": "123456789"
#     }
    
#     with patch("app.routes.extra_routes.Request.session", mock_session):
#         response = await client.post(
#             "/place_order",
#             data={"order_for": "2026-01-17"},
#             follow_redirects=False,
#         )
    
#     assert response.status_code == 302
