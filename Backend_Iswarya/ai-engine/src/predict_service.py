"""
Trained-model congestion prediction from the latest database reading (Intern 3, M4).

Adapted from traffic-monitoring/src/predict_service.py: production connects through
DATABASE_URL (Render Postgres) and falls back to the local POSTGRES_* settings.
"""

import os

import psycopg2

from predict import predict_congestion


def get_postgres_connection():
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg2.connect(url.replace("postgresql+psycopg2://", "postgresql://", 1))
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "traffic_monitoring"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "traffic123"),
    )


def get_congestion_prediction(road_id: str):
    """
    Fetch the latest traffic reading for a road and predict congestion with model-v1.
    Returns None when the road has no reading.
    """

    connection = get_postgres_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                tr.road_id,
                tr.vehicle_count,
                tr.avg_speed_kmph,
                tr.traffic_density_vehicles_per_km,
                tr.reading_timestamp,
                r.road_capacity,
                r.road_length_km
            FROM traffic_readings tr
            JOIN roads r
                ON tr.road_id = r.road_id
            WHERE tr.road_id = %s
            ORDER BY tr.reading_timestamp DESC, tr.reading_id DESC
            LIMIT 1
            """,
            (road_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        (
            road_id,
            vehicle_count,
            avg_speed_kmph,
            density,
            reading_timestamp,
            road_capacity,
            road_length_km,
        ) = row

        day_of_week = reading_timestamp.weekday()

        predicted_level, confidence = predict_congestion(
            vehicle_count=float(vehicle_count),
            density=float(density),
            avg_speed_kmph=float(avg_speed_kmph),
            road_capacity=float(road_capacity),
            road_length_km=float(road_length_km),
            hour=reading_timestamp.hour,
            day_of_week=day_of_week,
            is_weekend=int(day_of_week >= 5),
            road_id=road_id,
        )

        return {
            "road_id": road_id,
            "predicted_level": predicted_level,
            "confidence": round(confidence, 4),
            "generated_by": "model-v1",
        }

    finally:
        connection.close()
