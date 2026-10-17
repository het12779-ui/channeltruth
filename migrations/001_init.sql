-- ChannelTruth - SQL Server 2022 schema
--
-- The demo builds its schema from SQLAlchemy metadata for zero setup. This is
-- the equivalent DDL for the deployment target (MS SQL Server), with the
-- choices that matter for an attribution workload spelled out.

CREATE TABLE accounts (
    id            BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_accounts PRIMARY KEY,
    name          NVARCHAR(120) NOT NULL,
    slug          NVARCHAR(60)  NOT NULL,
    api_key_hash  CHAR(64)      NOT NULL,
    plan          NVARCHAR(30)  NOT NULL CONSTRAINT df_accounts_plan DEFAULT 'growth',
    created_at    DATETIME2(3)  NOT NULL CONSTRAINT df_accounts_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_accounts_slug UNIQUE (slug)
);

CREATE TABLE touchpoints (
    id           BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_touchpoints PRIMARY KEY,
    account_id   BIGINT       NOT NULL,
    event_uid    NVARCHAR(90) NOT NULL,
    visitor_id   NVARCHAR(90) NOT NULL,
    channel      NVARCHAR(40) NOT NULL,
    campaign     NVARCHAR(120) NULL,
    kind         NVARCHAR(20) NOT NULL CONSTRAINT df_touch_kind DEFAULT 'click',
    occurred_at  DATETIME2(3) NOT NULL,
    CONSTRAINT fk_touch_account FOREIGN KEY (account_id)
        REFERENCES accounts (id) ON DELETE CASCADE,
    -- At-least-once ingestion must not double count a touch.
    CONSTRAINT uq_touch_account_event UNIQUE (account_id, event_uid),
    CONSTRAINT ck_touch_kind CHECK (kind IN ('impression', 'click', 'visit'))
);

-- The journey query is "all touches for these visitors in this window".
-- Column order matters: account -> visitor -> time is the access path.
CREATE INDEX ix_touch_account_visitor_time
    ON touchpoints (account_id, visitor_id, occurred_at)
    INCLUDE (channel, kind);

CREATE INDEX ix_touch_account_time ON touchpoints (account_id, occurred_at);

CREATE TABLE conversions (
    id            BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_conversions PRIMARY KEY,
    account_id    BIGINT       NOT NULL,
    event_uid     NVARCHAR(90) NOT NULL,
    visitor_id    NVARCHAR(90) NOT NULL,
    revenue_cents BIGINT       NOT NULL,
    occurred_at   DATETIME2(3) NOT NULL,
    CONSTRAINT fk_conversion_account FOREIGN KEY (account_id)
        REFERENCES accounts (id) ON DELETE CASCADE,
    CONSTRAINT uq_conversion_account_event UNIQUE (account_id, event_uid),
    CONSTRAINT ck_conversion_revenue CHECK (revenue_cents > 0)
);

CREATE INDEX ix_conversion_account_time ON conversions (account_id, occurred_at);
CREATE INDEX ix_conversion_account_visitor ON conversions (account_id, visitor_id);

CREATE TABLE channel_spend (
    id          BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_channel_spend PRIMARY KEY,
    account_id  BIGINT       NOT NULL,
    channel     NVARCHAR(40) NOT NULL,
    [day]       DATE         NOT NULL,
    spend_cents BIGINT       NOT NULL,
    note        NVARCHAR(MAX) NULL,
    CONSTRAINT fk_spend_account FOREIGN KEY (account_id)
        REFERENCES accounts (id) ON DELETE CASCADE,
    -- Spend is restated by platforms; the unique key makes the correction an
    -- upsert instead of a duplicate row.
    CONSTRAINT uq_spend_account_channel_day UNIQUE (account_id, channel, [day]),
    CONSTRAINT ck_spend_non_negative CHECK (spend_cents >= 0)
);

CREATE INDEX ix_spend_account_day ON channel_spend (account_id, [day]);

-- Production note: at very high volume, `touchpoints` and `conversions` are
-- append-only and partition cleanly by month. A clustered columnstore index on
-- the fact tables (keeping the B-tree above for point lookups) is the usual
-- next step once a tenant passes a few hundred million touches.
