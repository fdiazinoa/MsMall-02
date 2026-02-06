
-- Enum for Table Startup Behavior
CREATE TYPE comportamiento_inicio_mesas_enum AS ENUM ('SIEMPRE_MOSTRAR', 'A_DEMANDA');

-- Add configuration column if it doesn't exist (assuming configuracion_terminal table exists, or we add to jsonb config?)
-- Based on previous conversations, config is often JSONB in 'locales' or 'terminals'.
-- But user asked to "Actualizar la tabla configuracion_terminal".
-- I will add a check to see if I need to alter a specific table or if this is just a conceptual change for the JSON.
-- However, for Safety, I will create the dedicated tables first.

CREATE TABLE IF NOT EXISTS rooms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    local_id UUID NOT NULL REFERENCES locales(id) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tables (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    pos_x INTEGER NOT NULL DEFAULT 0,
    pos_y INTEGER NOT NULL DEFAULT 0,
    shape VARCHAR(20) DEFAULT 'SQUARE', -- SQUARE, CIRCLE, OBSTACLE
    rotation INTEGER DEFAULT 0,
    width INTEGER DEFAULT 80,
    height INTEGER DEFAULT 80,
    capacity INTEGER DEFAULT 4,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster lookups
CREATE INDEX idx_tables_room_id ON tables(room_id);
