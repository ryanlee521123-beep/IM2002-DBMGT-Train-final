"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.
Updated to support fully normalized relational schema.
"""

import json
import os
import sys
import psycopg2
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    # Use ON CONFLICT DO NOTHING to avoid duplicate key errors on re-runs
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_stations_and_network(cur):
    """Handles both Metro and NR stations, plus lines and connections."""
    stations_rows = []
    lines_rows = []
    station_lines_rows = []
    connections_rows = []

    for filename in ["metro_stations.json", "national_rail_stations.json"]:
        data = load(filename)
        for item in data:
            sid = item.get("station_id")
            # 1. Stations
            stations_rows.append((
                sid,
                item.get("name"),
                item.get("is_interchange_metro", False),
                item.get("is_interchange_national_rail", False),
                item.get("interchange_national_rail_station_id"),
                item.get("interchange_metro_station_id")
            ))
            
            # 2. Lines & Mapping
            for line in item.get("lines", []):
                lines_rows.append((line, line))
                station_lines_rows.append((sid, line))
                
            # 3. Connections
            for adj in item.get("adjacent_stations", []):
                connections_rows.append((
                    sid, 
                    adj.get("station_id"), 
                    adj.get("line"), 
                    adj.get("travel_time_min")
                ))

    # Insert in correct dependency order
    insert_many(cur, "stations", ["station_id", "name", "is_interchange_metro", "is_interchange_national_rail", "interchange_national_rail_station_id", "interchange_metro_station_id"], stations_rows)
    insert_many(cur, "lines", ["line_id", "line_name"], lines_rows)
    insert_many(cur, "station_lines", ["station_id", "line_id"], station_lines_rows)
    insert_many(cur, "station_connections", ["from_station_id", "to_station_id", "line", "travel_time_min"], connections_rows)
    print("✅ 成功插入車站、路線與網路拓樸資料！")


def seed_schedules_and_fares(cur):
    """Handles both Metro and NR schedules, parsing arrays into normalized tables."""
    sched_rows = []
    stops_rows = []
    fares_rows = []
    days_rows = []

    for filename in ["metro_schedules.json", "national_rail_schedules.json"]:
        data = load(filename)
        for item in data:
            sch_id = item.get("schedule_id")
            
            # 1. Core Schedules
            sched_rows.append((
                sch_id, item.get("line"), item.get("service_type"), item.get("direction"),
                item.get("origin_station_id"), item.get("destination_station_id"),
                item.get("first_train_time"), item.get("last_train_time"), item.get("frequency_min")
            ))

            # 2. Schedule Stops
            stops = item.get("stops_in_order", [])
            tt_dict = item.get("travel_time_from_origin_min", {})
            for i, st in enumerate(stops):
                time_min = tt_dict.get(st, 0)
                stops_rows.append((sch_id, st, i+1, time_min))

            # 3. Schedule Fares (Metro uses base, NR uses fare_classes)
            if "base_fare_usd" in item:
                fares_rows.append((sch_id, "default", item.get("base_fare_usd"), item.get("per_stop_rate_usd")))
            elif "fare_classes" in item:
                for fc_name, fc_data in item["fare_classes"].items():
                    fares_rows.append((sch_id, fc_name, fc_data.get("base_fare_usd"), fc_data.get("per_stop_rate_usd")))

            # 4. Operating Days
            for day in item.get("operates_on", []):
                days_rows.append((sch_id, day))

    insert_many(cur, "schedules", ["schedule_id", "line", "service_type", "direction", "origin_station_id", "destination_station_id", "first_train_time", "last_train_time", "frequency_min"], sched_rows)
    insert_many(cur, "schedule_stops", ["schedule_id", "station_id", "stop_sequence", "time_from_origin_min"], stops_rows)
    insert_many(cur, "schedule_fares", ["schedule_id", "fare_class", "base_fare_usd", "per_stop_rate_usd"], fares_rows)
    insert_many(cur, "schedule_operating_days", ["schedule_id", "day_of_week"], days_rows)
    print("✅ 成功插入班次、停靠站、營運日與票價資料！")


def seed_seat_layouts(cur):
    """Parses nested layouts -> coaches -> seats."""
    data = load("national_rail_seat_layouts.json")
    layouts_rows = []
    coaches_rows = []
    seats_rows = []
    
    for layout in data:
        lid = layout.get("layout_id")
        layouts_rows.append((lid, layout.get("schedule_id")))
        
        for c in layout.get("coaches", []):
            coach = c.get("coach")
            coaches_rows.append((lid, coach, c.get("fare_class")))
            
            for s in c.get("seats", []):
                # Notice double quotes around row/column to bypass SQL keywords
                seats_rows.append((lid, coach, s.get("seat_id"), s.get("row"), s.get("column")))
                
    insert_many(cur, "train_layouts", ["layout_id", "schedule_id"], layouts_rows)
    insert_many(cur, "coaches", ["layout_id", "coach", "fare_class"], coaches_rows)
    insert_many(cur, "seats", ["layout_id", "coach", "seat_id", '"row"', '"column"'], seats_rows)
    print("✅ 成功插入列車座位配置資料！")


def seed_users(cur):
    data = load("registered_users.json")
    columns = [
        "user_id", "full_name", "email", "password", "phone",
        "date_of_birth", "secret_question", "secret_answer", "registered_at", "is_active"
    ]
    rows = []
    for user in data:
        rows.append((
            user.get("user_id"), user.get("full_name"), user.get("email"), user.get("password"), 
            user.get("phone"), user.get("date_of_birth"), user.get("secret_question"), 
            user.get("secret_answer"), user.get("registered_at"), user.get("is_active", True)
        ))
    insert_many(cur, "users", columns, rows)
    print("✅ 成功插入註冊使用者資料！")


def seed_bookings_and_history(cur):
    # 1. National Rail Bookings
    nr_data = load("bookings.json")
    nr_cols = [
        "booking_id", "user_id", "schedule_id", "origin_station_id", "destination_station_id",
        "travel_date", "departure_time", "ticket_type", "fare_class", "coach", "seat_id",
        "stops_travelled", "amount_usd", "status", "booked_at", "travelled_at"
    ]
    nr_rows = [tuple(item.get(col) for col in nr_cols) for item in nr_data]
    insert_many(cur, "bookings", nr_cols, nr_rows)
    
    # 2. Metro Travel History
    mt_data = load("metro_travel_history.json")
    mt_cols = [
        "trip_id", "user_id", "schedule_id", "origin_station_id", "destination_station_id",
        "travel_date", "ticket_type", "stops_travelled", "amount_usd",
        "status", "purchased_at", "travelled_at"
    ]
    mt_rows = [tuple(item.get(col) for col in mt_cols) for item in mt_data]
    insert_many(cur, "metro_travel_history", mt_cols, mt_rows)
    
    print("✅ 成功插入國鐵訂票與捷運乘車歷史！")


def seed_payments_and_feedback(cur):
    # 1. Payments
    pay_data = load("payments.json")
    pay_cols = ["payment_id", "booking_id", "amount_usd", "method", "status"]
    pay_rows = [tuple(item.get(col) for col in pay_cols) for item in pay_data]
    insert_many(cur, "payments", pay_cols, pay_rows)

    # 2. Feedback
    fb_data = load("feedback.json")
    fb_cols = ["feedback_id", "booking_id", "user_id", "rating", "comment", "submitted_at"]
    fb_rows = [tuple(item.get(col) for col in fb_cols) for item in fb_data]
    insert_many(cur, "feedback", fb_cols, fb_rows)
    
    print("✅ 成功插入支付與意見回饋資料！")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_stations_and_network(cur)
        seed_schedules_and_fares(cur)
        seed_seat_layouts(cur)
        seed_users(cur)
        seed_bookings_and_history(cur)
        seed_payments_and_feedback(cur)
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()