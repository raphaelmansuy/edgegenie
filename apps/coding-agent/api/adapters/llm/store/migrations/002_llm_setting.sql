-- 002_llm_setting.sql — settings an administrator chooses in the app, kept next to the catalogue.
--
-- One small key/value table rather than a column per setting: the first user is the default model, and
-- a second migration for every future setting would be ceremony. Values are plain configuration. A
-- secret never goes here (the KEK is outside the database, and keys are `llm_credential` rows).

CREATE TABLE IF NOT EXISTS llm.llm_setting (
    key         text        PRIMARY KEY,
    value       text        NOT NULL DEFAULT '',
    updated_by  text        NOT NULL DEFAULT '',
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT setting_no_key CHECK (value NOT LIKE '%sk-%' AND value NOT LIKE '%PRIVATE KEY%')
);

INSERT INTO llm.schema_version (version) VALUES (2) ON CONFLICT DO NOTHING;
