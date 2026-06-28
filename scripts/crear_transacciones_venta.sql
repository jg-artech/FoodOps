-- Migración: Tabla transacciones_venta
-- Ejecutar: psql -U <user> -d <db> -f scripts/crear_transacciones_venta.sql

CREATE TABLE IF NOT EXISTS transacciones_venta (
    id                      SERIAL PRIMARY KEY,
    punto_id                INTEGER NOT NULL REFERENCES puntos_venta(id),
    orden_id                INTEGER REFERENCES ordenes(id),

    tipo_venta              VARCHAR(20) NOT NULL DEFAULT 'individual',
    nombre_iniciativa       VARCHAR(100),

    cliente_nombre          VARCHAR(100),
    cliente_telefono        VARCHAR(20),
    cliente_direccion       TEXT,
    tipo_cliente            VARCHAR(20) NOT NULL DEFAULT 'para_llevar',

    precio_venta            NUMERIC(10,2) NOT NULL,
    costo_total             NUMERIC(10,2) NOT NULL DEFAULT 0,
    margen_bruto            NUMERIC(10,2) NOT NULL DEFAULT 0,
    margen_pct              NUMERIC(5,2)  NOT NULL DEFAULT 0,

    metodo_pago             VARCHAR(50),
    items_json              JSONB NOT NULL DEFAULT '[]',
    requerimientos_especiales TEXT,
    estado                  VARCHAR(50) NOT NULL DEFAULT 'completada',

    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tv_punto_id  ON transacciones_venta(punto_id);
CREATE INDEX IF NOT EXISTS idx_tv_fecha     ON transacciones_venta(created_at);
CREATE INDEX IF NOT EXISTS idx_tv_tipo      ON transacciones_venta(tipo_venta);
CREATE INDEX IF NOT EXISTS idx_tv_orden_id  ON transacciones_venta(orden_id);
