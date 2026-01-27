
-- Habilitar extensión para UUIDs si no está activa
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tabla de Roles
CREATE TABLE roles (
    id VARCHAR(50) PRIMARY KEY, -- 'admin', 'auditor', 'mall_manager'
    nombre VARCHAR(100) NOT NULL,
    permisos JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de Usuarios
CREATE TABLE usuarios (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255),
    rol_id VARCHAR(50) NOT NULL REFERENCES roles(id),
    estado VARCHAR(20) DEFAULT 'activo', -- 'activo', 'inactivo'
    ultimo_acceso TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de Centros Comerciales (Malls)
CREATE TABLE malls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre VARCHAR(255) NOT NULL,
    api_key VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de Locales dentro de los Malls
CREATE TABLE locales (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre VARCHAR(255) NOT NULL,
    mall_id UUID NOT NULL REFERENCES malls(id) ON DELETE CASCADE,
    codigo_interno VARCHAR(50) UNIQUE,
    responsable VARCHAR(255),
    contrato_no VARCHAR(100),
    piso VARCHAR(50),
    tipo_negocio VARCHAR(100),
    mts NUMERIC(10, 2),
    porciento_renta NUMERIC(5, 2),
    rubro VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de Ventas (Auditoría)
CREATE TABLE ventas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    local_id UUID NOT NULL REFERENCES locales(id) ON DELETE CASCADE,
    fecha DATE NOT NULL,
    total_bruto NUMERIC(15, 2) NOT NULL,
    total_impuestos NUMERIC(15, 2) NOT NULL,
    total_neto NUMERIC(15, 2) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices para optimización
CREATE INDEX idx_ventas_fecha ON ventas(fecha);
CREATE INDEX idx_usuarios_email ON usuarios(email);

-- Seed Data
INSERT INTO roles (id, nombre, permisos) VALUES 
('admin', 'Administrador Global', '["all"]'),
('auditor', 'Auditor de Ventas', '["view_reports", "ingest_data"]'),
('mall_manager', 'Gerente de Mall', '["view_reports", "manage_stores"]');

INSERT INTO usuarios (nombre, email, rol_id) VALUES 
('Administrador', 'admin@msmall.com', 'admin');
