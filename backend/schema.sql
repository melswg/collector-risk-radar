CREATE SCHEMA IF NOT EXISTS ml;
CREATE SCHEMA IF NOT EXISTS archive;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ml_reader') THEN
  CREATE ROLE ml_reader NOLOGIN;
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS archive.events (
 id text NOT NULL,
 channel_id integer NOT NULL,
 object_id text NOT NULL,
 ts timestamptz NOT NULL,
 value double precision NOT NULL,
 expected boolean NOT NULL,
 event text NOT NULL,
 severity text NOT NULL,
 raw jsonb,
 PRIMARY KEY (id,ts)
) PARTITION BY RANGE(ts);
DO $$ DECLARE m date; next_m date; BEGIN
 FOR m IN SELECT generate_series(date_trunc('month', now())-interval '13 years', date_trunc('month',now())+interval '1 year',interval '1 month')::date LOOP
 next_m := (m+interval '1 month')::date;
 EXECUTE format('CREATE TABLE IF NOT EXISTS archive.events_%s PARTITION OF archive.events FOR VALUES FROM (%L) TO (%L)',to_char(m,'YYYYMM'),m,next_m);
 END LOOP;
END $$;
CREATE OR REPLACE VIEW ml.objects AS SELECT * FROM public.objects;
CREATE OR REPLACE VIEW ml.alarms AS SELECT * FROM public.events WHERE severity='warning';
CREATE OR REPLACE VIEW ml.planned_works AS SELECT id,object_id,ts,available_at,data FROM public.records WHERE kind='work';
CREATE OR REPLACE VIEW ml.weather AS SELECT id,object_id,ts,available_at AS published_at,data FROM public.records WHERE kind='weather';
CREATE OR REPLACE VIEW ml.labels_incident AS SELECT id,object_id,ts AS start_ts,available_at,data FROM public.records WHERE kind='label' AND data->>'incident_type' IN ('fire','flood','intrusion');
CREATE OR REPLACE VIEW ml.labels_false_alarm AS SELECT id,object_id,ts,available_at,data FROM public.records WHERE kind='label' AND data->>'incident_type'='intrusion_false_alarm';
CREATE OR REPLACE VIEW ml.labels_sensor_failure AS SELECT id,object_id,ts,available_at,data FROM public.records WHERE kind='label' AND data->>'incident_type'='sensor_failure';
CREATE OR REPLACE VIEW ml.decisions AS SELECT * FROM public.decisions;
CREATE OR REPLACE VIEW ml.sensor_health AS SELECT id,object_id,ts,data FROM public.records WHERE kind='sensor_health';
CREATE MATERIALIZED VIEW IF NOT EXISTS ml.channel_agg_5m AS
SELECT channel_id,to_timestamp(floor(extract(epoch FROM ts)/300)*300) AS ts,
 min(value),max(value),avg(value) AS mean,stddev_pop(value) AS std,
 (array_agg(value ORDER BY ts))[1] AS first,(array_agg(value ORDER BY ts DESC))[1] AS last,
 count(*) AS count, greatest(0,1-count(*)::double precision) AS missing_fraction
FROM public.events GROUP BY channel_id,to_timestamp(floor(extract(epoch FROM ts)/300)*300);
CREATE UNIQUE INDEX IF NOT EXISTS agg_5m_key ON ml.channel_agg_5m(channel_id,ts);
CREATE MATERIALIZED VIEW IF NOT EXISTS ml.channel_agg_1h AS
SELECT channel_id,date_trunc('hour',ts) AS ts,
 min(value),max(value),avg(value) AS mean,stddev_pop(value) AS std,
 (array_agg(value ORDER BY ts))[1] AS first,(array_agg(value ORDER BY ts DESC))[1] AS last,
 count(*) AS count,greatest(0,1-count(*)::double precision/12) AS missing_fraction
FROM public.events GROUP BY channel_id,date_trunc('hour',ts);
CREATE UNIQUE INDEX IF NOT EXISTS agg_1h_key ON ml.channel_agg_1h(channel_id,ts);
CREATE OR REPLACE VIEW ml.label_windows AS
SELECT p.id AS prediction_id,p.object_id,p.incident_type,p.as_of,p.horizon_h,
CASE WHEN NOT EXISTS (SELECT 1 FROM public.records c WHERE c.kind='coverage' AND c.object_id=p.object_id AND (c.data->>'from')::timestamptz<=p.as_of AND (c.data->>'to')::timestamptz>=p.valid_until) THEN NULL
ELSE (EXISTS(SELECT 1 FROM public.records r WHERE r.kind='label' AND r.object_id=p.object_id AND r.data->>'incident_type'=p.incident_type AND r.ts>p.as_of AND r.ts<=p.valid_until))::integer END AS label
FROM public.predictions p;
REVOKE ALL ON SCHEMA ml FROM PUBLIC;
GRANT USAGE ON SCHEMA ml TO ml_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA ml TO ml_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA ml GRANT SELECT ON TABLES TO ml_reader;
