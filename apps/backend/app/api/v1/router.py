from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.exceptions.router import router as exceptions_router
from app.modules.health.router import router as health_router
from app.modules.ingestion.router import router as ingestion_router
from app.modules.line_stops.router import router as line_stops_router
from app.modules.microsoft.router import router as microsoft_router
from app.modules.rules.router import router as rules_router
from app.modules.shipments.router import router as shipments_router
from app.modules.stock.router import router as stock_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(tenants_router)
api_router.include_router(users_router)
api_router.include_router(ingestion_router)
api_router.include_router(line_stops_router)
api_router.include_router(microsoft_router)
api_router.include_router(shipments_router)
api_router.include_router(stock_router)
api_router.include_router(suppliers_router)
api_router.include_router(rules_router)
api_router.include_router(exceptions_router)
api_router.include_router(dashboard_router)
