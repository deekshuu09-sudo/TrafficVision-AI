"""
Reference-data bootstrap for a fresh production database.

Prediction and road-condition endpoints read the `roads` and `road_conditions` tables,
which the data-engineering pipeline normally creates. On a new managed Postgres (Render,
Neon) they may be missing, so on startup create them from the M2 schema and load the
bundled CSVs. Idempotent: DDL is IF NOT EXISTS and each table is only filled when empty.
"""

import csv
import logging
from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "M2_Day7_Traffic_Monitoring_" / "data"
ROADS_CSV = DATA_DIR / "traffic_monitoring_synthetic_dataset_with_density.csv"
CONDITIONS_CSV = DATA_DIR / "road_conditions.csv"

# Same definitions as data/M2_Day7_Traffic_Monitoring_/database/schema.sql and
# sql/m2_day4_road_conditions.sql.
ROADS_DDL = """
CREATE TABLE IF NOT EXISTS roads (
    road_id VARCHAR(20) PRIMARY KEY,
    road_name VARCHAR(150) NOT NULL,
    road_capacity INTEGER NOT NULL CHECK (road_capacity > 0),
    road_length_km NUMERIC(8,2) NOT NULL CHECK (road_length_km > 0),
    latitude NUMERIC(10,6),
    longitude NUMERIC(10,6)
)
"""
CONDITIONS_DDL = """
CREATE TABLE IF NOT EXISTS road_conditions (
    condition_id BIGSERIAL PRIMARY KEY,
    road_id VARCHAR(20) NOT NULL REFERENCES roads(road_id),
    condition_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    road_condition VARCHAR(50) NOT NULL,
    road_status VARCHAR(30) NOT NULL,
    incident_type VARCHAR(50),
    description TEXT,
    source VARCHAR(100) NOT NULL DEFAULT 'manual_or_external',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _is_empty(conn, table):
    return conn.execute(text(f"SELECT NOT EXISTS (SELECT 1 FROM {table})")).scalar()


def ensure_reference_data(engine):
    if engine.dialect.name != "postgresql":
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(ROADS_DDL))
            conn.execute(text(CONDITIONS_DDL))

            if _is_empty(conn, "roads") and ROADS_CSV.exists():
                roads = {}
                for row in _read_csv(ROADS_CSV):
                    roads.setdefault(
                        row["road_id"],
                        {
                            "road_id": row["road_id"],
                            "road_name": row["road_name"],
                            "road_capacity": int(row["road_capacity"]),
                            "road_length_km": float(row["road_length_km"]),
                            "latitude": float(row["latitude"]),
                            "longitude": float(row["longitude"]),
                        },
                    )
                conn.execute(
                    text(
                        "INSERT INTO roads (road_id, road_name, road_capacity, road_length_km,"
                        " latitude, longitude) VALUES (:road_id, :road_name, :road_capacity,"
                        " :road_length_km, :latitude, :longitude) ON CONFLICT (road_id) DO NOTHING"
                    ),
                    list(roads.values()),
                )
                logger.info("bootstrap: loaded %d roads", len(roads))

            if _is_empty(conn, "road_conditions") and CONDITIONS_CSV.exists():
                conditions = [
                    {**row, "incident_type": row["incident_type"] or None}
                    for row in _read_csv(CONDITIONS_CSV)
                ]
                conn.execute(
                    text(
                        "INSERT INTO road_conditions (road_id, condition_timestamp, road_condition,"
                        " road_status, incident_type, description, source) VALUES (:road_id,"
                        " :condition_timestamp, :road_condition, :road_status, :incident_type,"
                        " :description, :source)"
                    ),
                    conditions,
                )
                logger.info("bootstrap: loaded %d road conditions", len(conditions))
    except Exception:
        # Reference data must never stop the API from starting; the affected endpoints
        # report their own errors.
        logger.exception("bootstrap: could not prepare reference tables")
