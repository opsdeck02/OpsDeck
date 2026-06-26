from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.customer_health.router import router as customer_health_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.exceptions.router import router as exceptions_router
from app.modules.health.router import router as health_router
from app.modules.impact.router import router as impact_router
from app.modules.ingestion.router import router as ingestion_router
from app.modules.line_stops.router import router as line_stops_router
from app.modules.microsoft.router import router as microsoft_router
from app.modules.notifications.router import router as notifications_router
from app.modules.operational_history.router import router as operational_history_router
from app.modules.operational_reviews.router import router as operational_reviews_router
from app.modules.reports.router import router as reports_router
from app.modules.rules.router import router as rules_router
from app.modules.shipments.router import router as shipments_router
from app.modules.signal_engine.router import router as signal_engine_router
from app.modules.stock.router import router as stock_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tenants.router import router as tenants_router
from app.modules.tracking.router import router as tracking_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(customer_health_router)
api_router.include_router(tenants_router)
api_router.include_router(tracking_router)
api_router.include_router(users_router)
api_router.include_router(impact_router)
api_router.include_router(ingestion_router)
api_router.include_router(line_stops_router)
api_router.include_router(microsoft_router)
api_router.include_router(notifications_router)
api_router.include_router(operational_history_router)
api_router.include_router(operational_reviews_router)
api_router.include_router(shipments_router)
api_router.include_router(stock_router)
api_router.include_router(suppliers_router)
api_router.include_router(rules_router)
api_router.include_router(signal_engine_router)
api_router.include_router(reports_router)
api_router.include_router(exceptions_router)
api_router.include_router(dashboard_router)
