-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data you design below
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

-- ============================================================
--  STUDENT TASK — Design and create your relational tables here
--
--  Start from the mock data in train-mock-data/:
--    metro_stations.json, national_rail_stations.json
--    metro_schedules.json, national_rail_schedules.json
--    national_rail_seat_layouts.json
--    registered_users.json
--    bookings.json, metro_travel_history.json
--    payments.json, feedback.json
--
--  Think about:
--    - What tables do you need?
--    - What columns and data types?
--    - Which fields are primary keys? Which are foreign keys?
--    - What constraints make sense?
--
--  Apply your schema with:
--    docker-compose down -v && docker-compose up -d
-- ============================================================

--Core Network & Stations
CREATE TABLE stations (
    station_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    network_type VARCHAR(20) NOT NULL,
    is_interchange_metro BOOLEAN NOT NULL DEFAULT FALSE,
    is_interchange_national_rail BOOLEAN NOT NULL DEFAULT FALSE,
    linked_interchange_id VARCHAR(10) REFERENCES stations(station_id)
);

CREATE TABLE lines (
    line_id VARCHAR(10) PRIMARY KEY,
    line_name VARCHAR(50)
);

CREATE TABLE station_lines (
    station_id VARCHAR(10) REFERENCES stations(station_id),
    line_id VARCHAR(10) REFERENCES lines(line_id),
    PRIMARY KEY (station_id, line_id)
);

CREATE TABLE station_connections (
    from_station_id VARCHAR(10) REFERENCES stations(station_id),
    to_station_id VARCHAR(10) REFERENCES stations(station_id),
    line_id VARCHAR(10) REFERENCES lines(line_id),
    travel_time_min INT NOT NULL,
    PRIMARY KEY (from_station_id, to_station_id, line_id)
);

--Schedules & Fares
CREATE TABLE schedules (
    schedule_id VARCHAR(20) PRIMARY KEY,
    line_id VARCHAR(10) REFERENCES lines(line_id),
    service_type VARCHAR(50),
    direction VARCHAR(20) NOT NULL,
    origin_station_id VARCHAR(10) REFERENCES stations(station_id),
    destination_station_id VARCHAR(10) REFERENCES stations(station_id),
    first_train_time TIME NOT NULL,
    last_train_time TIME NOT NULL,
    frequency_min INT NOT NULL
);

CREATE TABLE schedule_stops (
    schedule_id VARCHAR(20) REFERENCES schedules(schedule_id),
    station_id VARCHAR(10) REFERENCES stations(station_id),
    stop_sequence INT NOT NULL,
    time_from_origin_min INT NOT NULL,
    PRIMARY KEY (schedule_id, station_id)
);

CREATE TABLE schedule_fares (
    schedule_id VARCHAR(20) REFERENCES schedules(schedule_id),
    fare_class VARCHAR(20),
    base_fare_usd DECIMAL(8,2) NOT NULL,
    per_stop_rate_usd DECIMAL(8,2) NOT NULL,
    PRIMARY KEY (schedule_id, fare_class)
);

CREATE TABLE schedule_operating_days (
    schedule_id VARCHAR(20) REFERENCES schedules(schedule_id),
    day_of_week VARCHAR(3),
    PRIMARY KEY (schedule_id, day_of_week)
);

--Seating & Layouts (National Rail)
CREATE TABLE train_layouts (
    layout_id VARCHAR(20) PRIMARY KEY,
    schedule_id VARCHAR(20) REFERENCES schedules(schedule_id)
);

CREATE TABLE coaches (
    coach_id SERIAL PRIMARY KEY,
    layout_id VARCHAR(20) REFERENCES train_layouts(layout_id),
    coach_label VARCHAR(5) NOT NULL,
    fare_class VARCHAR(20) NOT NULL
);

CREATE TABLE seats (
    seat_pk SERIAL PRIMARY KEY,
    coach_id INT REFERENCES coaches(coach_id),
    seat_label VARCHAR(10) NOT NULL,
    row_num INT NOT NULL,
    column_label VARCHAR(2) NOT NULL
);

--Users & Authentication
CREATE TABLE users (
    user_id VARCHAR(20) PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(20),
    date_of_birth DATE,
    registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE user_credentials (
    user_id VARCHAR(20) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    password_hash VARCHAR(255) NOT NULL,
    secret_question TEXT,
    secret_answer_hash VARCHAR(255),
    last_password_change TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

--Bookings, Payments, & Feedback
CREATE TABLE bookings (
    booking_id VARCHAR(20) PRIMARY KEY,
    user_id VARCHAR(20) REFERENCES users(user_id),
    schedule_id VARCHAR(20) REFERENCES schedules(schedule_id),
    origin_station_id VARCHAR(10) REFERENCES stations(station_id),
    destination_station_id VARCHAR(10) REFERENCES stations(station_id),
    travel_date DATE NOT NULL,
    departure_time TIME,
    ticket_type VARCHAR(20) NOT NULL,
    fare_class VARCHAR(20),
    seat_pk INT REFERENCES seats(seat_pk),
    stops_travelled INT NOT NULL,
    amount_usd DECIMAL(8,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    booked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    travelled_at TIMESTAMP
);

CREATE TABLE payments (
    payment_id VARCHAR(20) PRIMARY KEY,
    booking_id VARCHAR(20) NOT NULL REFERENCES bookings(booking_id),
    amount_usd DECIMAL(8,2) NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    payment_status VARCHAR(20) NOT NULL,
    transaction_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feedback (
    feedback_id VARCHAR(20) PRIMARY KEY,
    booking_id VARCHAR(20) REFERENCES bookings(booking_id),
    user_id VARCHAR(20) REFERENCES users(user_id),
    rating INT CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    -- 768-dim  → Ollama nomic-embed-text (default)
    -- 3072-dim → Gemini gemini-embedding-001
    -- If you switch LLM_PROVIDER to gemini, change to vector(3072) and reset the database.
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS ON policy_documents USING hnsw (embedding vector_cosine_ops);
