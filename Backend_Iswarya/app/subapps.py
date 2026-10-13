"""
Analytics (Intern 2) and AI Engine (Intern 3) served from the backend process.

Render's free tier gives one web service per URL, so the frontend reaches these services
through the gateway paths it already uses: `<site>/analytics/...` and `<site>/ai-engine/...`.
Each service is an unchanged FastAPI app with its own flat `src/` modules; some module names
overlap (redis_cache, congestion_calculator), so each one is imported in isolation.
A service that fails to load is skipped and logged; the core API keeps running.
"""

import csv
import importlib
import importlib.util
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_DIR = ROOT / "services" / "analytics"
AI_ENGINE_DIR = ROOT / "ai-engine"

# Same order as QA/milestone4/day3/setup_production_db.py.
ANALYTICS_SCHEMA = [
    ANALYTICS_DIR / "database" / "schema.sql",
    ANALYTICS_DIR / "sql" / "milestone_2_schema.sql",
    ANALYTICS_DIR / "sql" / "m2_day5_aggregation.sql",
    ANALYTICS_DIR / "sql" / "m3_day5_analytics_optimization.sql",
]


@contextmanager
def isolated_imports(src_dir):
    """Import a service's flat modules from `src_dir` without leaking them to other services."""
    names = {p.stem for p in Path(src_dir).glob("*.py")}
    shadowed = {name: sys.modules.pop(name) for name in list(sys.modules) if name in names}
    before = set(sys.modules)
    sys.path.insert(0, str(src_dir))
    try:
        yield
    finally:
        sys.path.remove(str(src_dir))
        for name in set(sys.modules) - before:
            if name in names:
                sys.modules.pop(name, None)
        sys.modules.update(shadowed)


def _count(conn, table):
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        return cur.fetchone()[0]


def _load_live_readings(conn):
    """Live readings from the synthetic dataset, as setup_production_db.py loads them."""
    from psycopg2.extras import execute_batch

    calculate_congestion = importlib.import_module("congestion_calculator").calculate_congestion
    path = ANALYTICS_DIR / "data" / "traffic_monitoring_synthetic_dataset_with_density.csv"
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    readings = [
        (
            row["road_id"],
            row["sensor_id"],
            row["timestamp"],
            int(row["vehicle_count"]),
            float(row["avg_speed_kmph"]),
            int(row["road_capacity"]),
            float(row["traffic_density_vehicles_per_km"]),
            # Same rule as the ingestion service (src/traffic_ingestion.py).
            calculate_congestion(int(row["vehicle_count"]), int(row["road_capacity"])),
            float(row["latitude"]),
            float(row["longitude"]),
        )
        for row in rows
    ]
    with conn.cursor() as cur:
        execute_batch(
            cur,
            "INSERT INTO traffic_readings (road_id, sensor_id, reading_timestamp, vehicle_count,"
            " avg_speed_kmph, road_capacity, traffic_density_vehicles_per_km, congestion_level,"
            " latitude, longitude) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            readings,
            page_size=500,
        )
    logger.info("analytics data: loaded %d traffic_readings", len(readings))


def prepare_analytics_data():
    """Create the analytics tables and load history + aggregates when they are empty."""
    if not os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql")):
        return
    src = ANALYTICS_DIR / "src"
    try:
        with isolated_imports(src):
            database = importlib.import_module("database")
            conn = database.get_postgres_connection()
            try:
                for path in ANALYTICS_SCHEMA:
                    # psql meta-commands (\set ...) are not SQL; drop them.
                    sql = "\n".join(
                        line
                        for line in path.read_text(encoding="utf-8").splitlines()
                        if not line.startswith("\\")
                    )
                    try:
                        with conn.cursor() as cur:
                            cur.execute(sql)
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        logger.exception("analytics schema: %s failed", path.name)

                if not _count(conn, "traffic_readings"):
                    _load_live_readings(conn)
                conn.commit()

                for table, loader in (
                    ("traffic_history", "load_historical_data"),
                    ("hourly_traffic_metrics", "generate_traffic_aggregates"),
                ):
                    if _count(conn, table):
                        conn.commit()
                        continue
                    conn.commit()
                    importlib.import_module(loader).main()
                    logger.info("analytics data: loaded %s", table)
            finally:
                conn.close()
    except Exception:
        logger.exception("analytics data: preparation failed")


def _load_entry(path, module_name):
    """Load a service's entry file under a unique name (the AI engine's is `app.py`, which
    would otherwise resolve to this backend's own `app` package)."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


def mount_services(app):
    try:
        with isolated_imports(ANALYTICS_DIR / "src"):
            analytics = _load_entry(ANALYTICS_DIR / "src" / "main.py", "analytics_service_main")
        app.mount("/analytics", analytics, name="analytics")
    except Exception:
        logger.exception("analytics service not mounted")

    # The AI engine reads live traffic from this same process.
    os.environ.setdefault(
        "TRAFFIC_API_URL",
        f"http://127.0.0.1:{os.getenv('PORT', '8000')}/api/v1/traffic/live",
    )
    try:
        with isolated_imports(AI_ENGINE_DIR / "src"):
            ai_engine = _load_entry(AI_ENGINE_DIR / "app.py", "ai_engine_app")
        app.mount("/ai-engine", ai_engine, name="ai-engine")
    except Exception:
        logger.exception("AI engine not mounted")
