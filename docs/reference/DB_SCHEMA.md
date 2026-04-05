# Aracne2 — PostgreSQL Platform Schema (Layer 1)
# Reference only. Do not send as a prompt — use when implementing migrations or models.

## Extensions

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
```

## Enum types

```sql
CREATE TYPE role_name AS ENUM
  ('Admin', 'EditorInChief', 'Designer', 'Editor', 'User');

CREATE TYPE plugin_status AS ENUM ('active', 'inactive', 'error');
```

## Tables

```sql
-- roles
CREATE TABLE roles (
  id          SMALLSERIAL  PRIMARY KEY,
  name        role_name    NOT NULL UNIQUE,
  description TEXT,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- users
CREATE TABLE users (
  id             UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  username       VARCHAR(64)  NOT NULL UNIQUE,
  email          VARCHAR(255) NOT NULL UNIQUE,
  password_hash  TEXT         NOT NULL,
  display_name   VARCHAR(128),
  preferred_lang CHAR(5)      NOT NULL DEFAULT 'it',
  is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
  is_verified    BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  last_login_at  TIMESTAMPTZ,
  deleted_at     TIMESTAMPTZ
);

-- user_roles
CREATE TABLE user_roles (
  id          BIGSERIAL    PRIMARY KEY,
  user_id     UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id     SMALLINT     NOT NULL REFERENCES roles(id),
  assigned_by UUID         REFERENCES users(id) ON DELETE SET NULL,
  assigned_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  revoked_at  TIMESTAMPTZ,
  revoked_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
  notes       TEXT,
  CONSTRAINT uq_user_active_role
    UNIQUE NULLS NOT DISTINCT (user_id, role_id, revoked_at)
);

-- sessions
CREATE TABLE sessions (
  id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  access_jti      UUID         NOT NULL UNIQUE,
  refresh_jti     UUID         UNIQUE,
  ip_address      INET,
  user_agent      TEXT,
  issued_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  access_expires  TIMESTAMPTZ  NOT NULL,
  refresh_expires TIMESTAMPTZ,
  revoked_at      TIMESTAMPTZ,
  revoked_reason  VARCHAR(64)
);

-- system_settings
CREATE TABLE system_settings (
  key         VARCHAR(256) PRIMARY KEY,
  value       TEXT         NOT NULL,
  type        VARCHAR(32)  NOT NULL DEFAULT 'string',
  description TEXT,
  updated_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- audit_log
CREATE TABLE audit_log (
  id             BIGSERIAL    PRIMARY KEY,
  action         VARCHAR(128) NOT NULL,
  actor_id       UUID         REFERENCES users(id) ON DELETE SET NULL,
  actor_username VARCHAR(64),
  target_type    VARCHAR(64),
  target_id      TEXT,
  target_label   TEXT,
  ip_address     INET,
  user_agent     TEXT,
  payload        JSONB,
  occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- plugins
CREATE TABLE plugins (
  id           UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
  name         VARCHAR(128)  NOT NULL UNIQUE,
  display_name VARCHAR(256)  NOT NULL,
  version      VARCHAR(32),
  description  TEXT,
  author       VARCHAR(256),
  entry_point  TEXT,
  status       plugin_status NOT NULL DEFAULT 'inactive',
  config       JSONB         NOT NULL DEFAULT '{}',
  hooks        JSONB         NOT NULL DEFAULT '[]',
  installed_at TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  installed_by UUID          REFERENCES users(id) ON DELETE SET NULL
);

-- notifications
CREATE TABLE notifications (
  id         BIGSERIAL    PRIMARY KEY,
  user_id    UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type       VARCHAR(128) NOT NULL,
  title      VARCHAR(512) NOT NULL,
  body       TEXT,
  link       TEXT,
  is_read    BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  read_at    TIMESTAMPTZ
);
```

## Triggers

```sql
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- Assigns the 'User' role automatically on every new user insert.
CREATE OR REPLACE FUNCTION fn_assign_default_role()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO user_roles (user_id, role_id)
  SELECT NEW.id, id FROM roles WHERE name = 'User';
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_default_role
  AFTER INSERT ON users
  FOR EACH ROW EXECUTE FUNCTION fn_assign_default_role();
```

## Privacy notes

- `ip_address` and `user_agent` in `sessions` and `audit_log` are personal data.
- Their retention is controlled via `system_settings`:
  - `audit_log_retention_days` (default: 90)
  - `expired_sessions_retention_days` (default: 30)
- These fields must never appear in API responses.
