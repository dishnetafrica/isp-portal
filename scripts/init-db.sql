-- ISP Portal Database Initialization

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    uisp_customer_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    phone VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_customers_uisp_id ON customers(uisp_customer_id);
CREATE INDEX idx_customers_email ON customers(email);

-- Customer devices table
CREATE TABLE IF NOT EXISTS customer_devices (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    device_type VARCHAR(50) NOT NULL,
    device_identifier VARCHAR(255) NOT NULL,
    nickname VARCHAR(100),
    
    -- MikroTik specific
    mikrotik_host VARCHAR(255),
    mikrotik_api_user VARCHAR(100),
    mikrotik_api_password_encrypted TEXT,
    
    -- TR-069 specific
    tr069_device_id VARCHAR(255),
    
    -- Metadata
    last_seen TIMESTAMP WITH TIME ZONE,
    config_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_devices_customer ON customer_devices(customer_id);
CREATE INDEX idx_devices_type ON customer_devices(device_type);

-- Hotspot vouchers table
CREATE TABLE IF NOT EXISTS hotspot_vouchers (
    id SERIAL PRIMARY KEY,
    customer_device_id INTEGER REFERENCES customer_devices(id) ON DELETE CASCADE,
    voucher_code VARCHAR(50) UNIQUE NOT NULL,
    profile VARCHAR(100),
    validity VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_vouchers_code ON hotspot_vouchers(voucher_code);
CREATE INDEX idx_vouchers_device ON hotspot_vouchers(customer_device_id);

-- UISP cache table
CREATE TABLE IF NOT EXISTS uisp_cache (
    id SERIAL PRIMARY KEY,
    uisp_customer_id VARCHAR(255) NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    data JSONB NOT NULL,
    cached_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_cache_customer ON uisp_cache(uisp_customer_id);
CREATE INDEX idx_cache_type ON uisp_cache(data_type);
CREATE INDEX idx_cache_expires ON uisp_cache(expires_at);

-- Audit logs table
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    details JSONB,
    ip_address VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_customer ON audit_logs(customer_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_created ON audit_logs(created_at);

-- Session tokens table (for refresh tokens)
CREATE TABLE IF NOT EXISTS session_tokens (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    device_info JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE,
    is_revoked BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_session_customer ON session_tokens(customer_id);
CREATE INDEX idx_session_token ON session_tokens(token_hash);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables with updated_at
CREATE TRIGGER update_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_devices_updated_at
    BEFORE UPDATE ON customer_devices
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Clean up expired cache entries (run periodically)
CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS void AS $$
BEGIN
    DELETE FROM uisp_cache WHERE expires_at < CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- Clean up expired sessions
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void AS $$
BEGIN
    DELETE FROM session_tokens WHERE expires_at < CURRENT_TIMESTAMP OR is_revoked = TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE customers IS 'Customer accounts linked to UISP';
COMMENT ON TABLE customer_devices IS 'Customer network devices (Starlink, MikroTik, TR-069)';
COMMENT ON TABLE hotspot_vouchers IS 'Generated hotspot vouchers for MikroTik';
COMMENT ON TABLE audit_logs IS 'Audit trail of customer actions';
