-- Handy queries once the stack is running:  docker compose exec db psql -U aml -d aml

-- Customers by rating
SELECT * FROM v_risk_distribution;

-- Who is waiting on an analyst?
SELECT * FROM v_open_screening_matches;
SELECT * FROM v_reviews_pending;

-- Every rating change with its trigger
SELECT * FROM v_rating_changes;

-- Audit trail for one customer
SELECT ts, actor_type, actor, action, details FROM audit_log WHERE customer_id = 1 ORDER BY id;

-- Which actions did AI vs humans perform?
SELECT actor_type, action, COUNT(*) FROM audit_log GROUP BY 1, 2 ORDER BY 1, 3 DESC;

-- Risk component breakdown from the latest risk assessment
SELECT c.customer_ref, c.full_name, a.output ->> 'risk_rating' AS rating, a.output -> 'components' AS components
FROM v_latest_assessments a JOIN customers c ON c.id = a.customer_id
WHERE a.agent = 'risk';

-- Phase 2 ---------------------------------------------------------------------------------------
-- Corporates that are not yet fully UBO-verified and rated HIGH or above
SELECT corp_ref, legal_name, risk_rating, risk_score FROM corporates WHERE risk_rating IN ('HIGH','PROHIBITED') ORDER BY risk_score DESC;
-- Highest-risk wallets and who owns them
SELECT * FROM v_wallet_risk ORDER BY risk_score DESC NULLS LAST LIMIT 10;
-- Travel Rule exceptions awaiting action
SELECT * FROM v_travel_rule_exceptions ORDER BY created_at DESC;
-- MLRO escalation queue
SELECT * FROM v_mlro_queue;
-- SAR pipeline and QA error rates
SELECT * FROM v_sar_pipeline;
SELECT * FROM v_qa_by_analyst ORDER BY failed DESC;
