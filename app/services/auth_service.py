from fastapi import Request


class AuthService:
    @staticmethod
    async def ensure_admin(request: Request) -> bool:
        cashier_id = request.session.get('cashier_id')
        if not cashier_id:
            return False

        async with request.app.state.db.acquire() as conn:
            cashier = await conn.fetchrow(
                'SELECT is_admin FROM cashiers WHERE id = $1',
                cashier_id,
            )
            return bool(cashier and cashier['is_admin'])
