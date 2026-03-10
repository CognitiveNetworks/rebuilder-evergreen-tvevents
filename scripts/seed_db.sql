-- Seed data for local development
-- Creates the blacklisted station channel map table

CREATE TABLE IF NOT EXISTS public.tvevents_blacklisted_station_channel_map (
    id SERIAL PRIMARY KEY,
    channel_id VARCHAR(50) NOT NULL,
    station_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Insert sample blacklisted channels for development
INSERT INTO public.tvevents_blacklisted_station_channel_map (channel_id, station_id) VALUES
    ('12345', 'STATION_A'),
    ('67890', 'STATION_B'),
    ('11111', 'STATION_C'),
    ('12345', 'STATION_D')
ON CONFLICT DO NOTHING;
