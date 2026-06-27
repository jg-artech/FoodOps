"""Ejecuta el seed demo de FoodOps."""

import asyncio

from foodops.db.database import AsyncSessionLocal
from foodops.db.seed import seed_demo_data


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await seed_demo_data(db)

    if result.created:
        print(
            "Seed demo creado: "
            f"{result.puntos_venta} puntos de venta, {result.usuarios} usuarios."
        )
        return

    print(f"Seed demo ya existe para empresa NIT {result.empresa_nit}.")


if __name__ == "__main__":
    asyncio.run(main())
