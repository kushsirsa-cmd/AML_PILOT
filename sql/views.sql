-- Reporting views used for ad-hoc analysis (the application computes the dashboard in Python, these mirror it in SQL).

CREATE OR REPLACE VIEW v_risk_distribution AS
SELECT COALESCE(risk_rating, 'UNRATED') AS risk_rating, COUNT(*) AS customers
FROM customers
GROUP BY COALESCE(risk_rating, 'UNRATED');

CREATE OR REPLACE VIEW v_open_screening_matches AS
SELECT h.id AS hit_id, c.customer_ref, c.full_name, h.list_type, h.matched_name, h.confidence, h.disposition, h.created_at
FROM screening_hits h
JOIN customers c ON c.id = h.customer_id
WHERE h.disposition = 'OPEN' AND h.confidence >= 75
ORDER BY h.confidence DESC;

CREATE OR REPLACE VIEW v_reviews_pending AS
SELECT r.id AS review_id, c.customer_ref, c.full_name, r.review_type, r.trigger, r.recommendation, r.created_at
FROM reviews r
JOIN customers c ON c.id = r.customer_id
WHERE r.status = 'PENDING'
ORDER BY r.created_at DESC;

CREATE OR REPLACE VIEW v_reviews_overdue AS
SELECT customer_ref, full_name, risk_rating, next_review_due, CURRENT_DATE - next_review_due AS days_overdue
FROM customers
WHERE next_review_due < CURRENT_DATE AND status IN ('ACTIVE', 'UNDER_REVIEW')
ORDER BY next_review_due;

CREATE OR REPLACE VIEW v_rating_changes AS
SELECT ts, customer_id, actor,
       details ->> 'from' AS from_rating, details ->> 'to' AS to_rating,
       details ->> 'score' AS score, details ->> 'trigger' AS trigger
FROM audit_log
WHERE action IN ('RISK_RATING_ASSIGNED', 'RISK_RATING_CHANGED')
ORDER BY ts DESC;

CREATE OR REPLACE VIEW v_latest_assessments AS
SELECT DISTINCT ON (customer_id, agent) customer_id, agent, engine, output, created_at
FROM assessments
ORDER BY customer_id, agent, id DESC;

-- ---------------------------------------------------------------------------------------------
-- Phase 2 views
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_mlro_queue AS
SELECT a.id AS alert_id, a.severity, a.source, a.title, a.status, a.assigned_to, a.escalated_at, a.sar_id,
       EXTRACT(DAY FROM now() - a.created_at)::int AS age_days
FROM alerts a
WHERE a.status IN ('ESCALATED_MLRO', 'SAR_DRAFTED')
ORDER BY CASE a.severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 ELSE 2 END, a.id;

CREATE OR REPLACE VIEW v_wallet_risk AS
SELECT w.id AS wallet_id, w.address, w.chain, w.risk_level, w.risk_score, w.self_hosted, w.last_screened_at,
       c.full_name AS customer, k.legal_name AS corporate
FROM wallets w
LEFT JOIN customers c ON c.id = w.customer_id
LEFT JOIN corporates k ON k.id = w.corporate_id;

CREATE OR REPLACE VIEW v_travel_rule_exceptions AS
SELECT id, direction, amount_eur, asset, counterparty_vasp, status, reasons, created_at
FROM travel_rule_transfers
WHERE status IN ('HOLD_REQUEST_INFO', 'REJECT');

CREATE OR REPLACE VIEW v_sar_pipeline AS
SELECT status, count(*) AS sars, COALESCE(sum(total_amount_eur), 0) AS total_eur
FROM sars GROUP BY status;

CREATE OR REPLACE VIEW v_qa_by_analyst AS
SELECT decision_maker, count(*) AS sampled,
       count(*) FILTER (WHERE status = 'COMPLETED') AS completed,
       count(*) FILTER (WHERE outcome = 'FAIL') AS failed,
       round(100.0 * count(*) FILTER (WHERE outcome = 'PASS') / NULLIF(count(*) FILTER (WHERE status = 'COMPLETED'), 0), 1) AS pass_rate_pct
FROM qa_reviews GROUP BY decision_maker;
