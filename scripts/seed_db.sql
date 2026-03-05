-- Seed data for local development
-- Mirrors the production tvevents_blacklisted_station_channel_map table

CREATE TABLE IF NOT EXISTS public.tvevents_blacklisted_station_channel_map (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) NOT NULL,
    channel_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert realistic blacklisted channels for local testing
INSERT INTO public.tvevents_blacklisted_station_channel_map (station_id, channel_id) VALUES
    ('STATION_001', '501'),
    ('STATION_001', '502'),
    ('STATION_002', '701'),
    ('STATION_003', '888'),
    ('STATION_004', '999')
ON CONFLICT DO NOTHING;
