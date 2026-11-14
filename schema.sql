-- AML Copilot MVP - PostgreSQL schema
-- Generated from backend/app/models.py via backend/scripts/dump_schema.py. Safe to run on an empty database.

CREATE TABLE IF NOT EXISTS address_labels (
	address VARCHAR(100) NOT NULL, 
	chain VARCHAR(10) NOT NULL, 
	category VARCHAR(30) NOT NULL, 
	entity_name VARCHAR(200) NOT NULL, 
	source VARCHAR(60) NOT NULL, 
	PRIMARY KEY (address)
);

CREATE INDEX IF NOT EXISTS ix_address_labels_category ON address_labels (category);

CREATE TABLE IF NOT EXISTS alerts (
	id SERIAL NOT NULL, 
	source VARCHAR(30) NOT NULL, 
	entity_type VARCHAR(20) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	customer_id INTEGER, 
	severity VARCHAR(10) NOT NULL, 
	title VARCHAR(250) NOT NULL, 
	description TEXT NOT NULL, 
	details JSONB NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	assigned_to VARCHAR(100), 
	escalated_at TIMESTAMP WITH TIME ZONE, 
	sar_id INTEGER, 
	resolution TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_alerts_customer_id ON alerts (customer_id);
CREATE INDEX IF NOT EXISTS ix_alerts_source ON alerts (source);
CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts (status);

CREATE TABLE IF NOT EXISTS analyses (
	id SERIAL NOT NULL, 
	entity_type VARCHAR(20) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	engine VARCHAR(30) NOT NULL, 
	output JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_analyses_entity ON analyses (entity_type, entity_id, kind);

CREATE TABLE IF NOT EXISTS audit_log (
	id SERIAL NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	actor VARCHAR(100) NOT NULL, 
	actor_type VARCHAR(10) NOT NULL, 
	action VARCHAR(60) NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	entity_id VARCHAR(60), 
	customer_id INTEGER, 
	details JSONB NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_audit_customer_ts ON audit_log (customer_id, ts);
CREATE INDEX IF NOT EXISTS ix_audit_log_action ON audit_log (action);
CREATE INDEX IF NOT EXISTS ix_audit_log_actor_type ON audit_log (actor_type);
CREATE INDEX IF NOT EXISTS ix_audit_log_ts ON audit_log (ts);

CREATE TABLE IF NOT EXISTS chain_txs (
	id SERIAL NOT NULL, 
	tx_hash VARCHAR(80) NOT NULL, 
	chain VARCHAR(10) NOT NULL, 
	from_address VARCHAR(100) NOT NULL, 
	to_address VARCHAR(100) NOT NULL, 
	asset VARCHAR(10) NOT NULL, 
	amount FLOAT NOT NULL, 
	amount_eur FLOAT NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (tx_hash)
);

CREATE INDEX IF NOT EXISTS ix_chain_from ON chain_txs (from_address);
CREATE INDEX IF NOT EXISTS ix_chain_to ON chain_txs (to_address);
CREATE INDEX IF NOT EXISTS ix_chain_txs_ts ON chain_txs (ts);

CREATE TABLE IF NOT EXISTS corporates (
	id SERIAL NOT NULL, 
	corp_ref VARCHAR(32) NOT NULL, 
	legal_name VARCHAR(250) NOT NULL, 
	registration_number VARCHAR(60), 
	country_of_incorporation VARCHAR(100) NOT NULL, 
	entity_type VARCHAR(50) NOT NULL, 
	industry VARCHAR(200) NOT NULL, 
	incorporation_date DATE, 
	registered_address TEXT, 
	operating_countries TEXT, 
	annual_turnover FLOAT, 
	employees INTEGER, 
	expected_activity TEXT, 
	listed BOOLEAN NOT NULL, 
	has_bearer_shares BOOLEAN NOT NULL, 
	nominee_directors BOOLEAN NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	risk_rating VARCHAR(20), 
	risk_score INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_corporates_corp_ref ON corporates (corp_ref);
CREATE INDEX IF NOT EXISTS ix_corporates_legal_name ON corporates (legal_name);
CREATE INDEX IF NOT EXISTS ix_corporates_risk_rating ON corporates (risk_rating);
CREATE INDEX IF NOT EXISTS ix_corporates_status ON corporates (status);

CREATE TABLE IF NOT EXISTS customers (
	id SERIAL NOT NULL, 
	customer_ref VARCHAR(32) NOT NULL, 
	full_name VARCHAR(200) NOT NULL, 
	date_of_birth DATE NOT NULL, 
	nationality VARCHAR(100) NOT NULL, 
	country_of_residence VARCHAR(100) NOT NULL, 
	address TEXT, 
	occupation VARCHAR(200) NOT NULL, 
	industry VARCHAR(200) NOT NULL, 
	source_of_funds TEXT, 
	source_of_wealth TEXT, 
	expected_activity TEXT, 
	annual_income FLOAT, 
	product VARCHAR(50) NOT NULL, 
	channel VARCHAR(50) NOT NULL, 
	pep_declared BOOLEAN NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	risk_rating VARCHAR(20), 
	risk_score INTEGER, 
	onboarded_at DATE, 
	last_kyc_review DATE, 
	next_review_due DATE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_customer_ref ON customers (customer_ref);
CREATE INDEX IF NOT EXISTS ix_customers_full_name ON customers (full_name);
CREATE INDEX IF NOT EXISTS ix_customers_risk_rating ON customers (risk_rating);
CREATE INDEX IF NOT EXISTS ix_customers_status ON customers (status);

CREATE TABLE IF NOT EXISTS entity_identifiers (
	id SERIAL NOT NULL, 
	entity_type VARCHAR(10) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	kind VARCHAR(15) NOT NULL, 
	value VARCHAR(200) NOT NULL, 
	source VARCHAR(40) NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_ident_entity ON entity_identifiers (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_ident_kind_value ON entity_identifiers (kind, value);

CREATE TABLE IF NOT EXISTS investigations (
	id SERIAL NOT NULL, 
	reference VARCHAR(30) NOT NULL, 
	title VARCHAR(250) NOT NULL, 
	source_type VARCHAR(15) NOT NULL, 
	alert_id INTEGER, 
	entity_type VARCHAR(10) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	customer_id INTEGER, 
	priority VARCHAR(10) NOT NULL, 
	queue VARCHAR(12) NOT NULL, 
	step INTEGER NOT NULL, 
	assigned_to VARCHAR(100), 
	opened_by VARCHAR(100) NOT NULL, 
	escalated_by VARCHAR(100), 
	confidence INTEGER, 
	risk_score INTEGER, 
	typologies JSONB NOT NULL, 
	agents JSONB NOT NULL, 
	notes JSONB NOT NULL, 
	disposition VARCHAR(30), 
	closure_rationale TEXT, 
	sar_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (reference)
);

CREATE INDEX IF NOT EXISTS ix_investigations_alert_id ON investigations (alert_id);
CREATE INDEX IF NOT EXISTS ix_investigations_customer_id ON investigations (customer_id);
CREATE INDEX IF NOT EXISTS ix_investigations_queue ON investigations (queue);

CREATE TABLE IF NOT EXISTS qa_reviews (
	id SERIAL NOT NULL, 
	audit_id INTEGER NOT NULL, 
	decision_action VARCHAR(60) NOT NULL, 
	decision_maker VARCHAR(100) NOT NULL, 
	customer_id INTEGER, 
	risk_rating VARCHAR(20), 
	summary TEXT NOT NULL, 
	status VARCHAR(15) NOT NULL, 
	precheck JSONB NOT NULL, 
	checklist JSONB NOT NULL, 
	score FLOAT, 
	outcome VARCHAR(25), 
	findings TEXT, 
	reviewer VARCHAR(100), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (audit_id)
);

CREATE INDEX IF NOT EXISTS ix_qa_reviews_decision_action ON qa_reviews (decision_action);
CREATE INDEX IF NOT EXISTS ix_qa_reviews_decision_maker ON qa_reviews (decision_maker);
CREATE INDEX IF NOT EXISTS ix_qa_reviews_status ON qa_reviews (status);

CREATE TABLE IF NOT EXISTS regulatory_reports (
	id SERIAL NOT NULL, 
	report_type VARCHAR(40) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	period_start DATE NOT NULL, 
	period_end DATE NOT NULL, 
	status VARCHAR(15) NOT NULL, 
	payload JSONB NOT NULL, 
	generated_by VARCHAR(100) NOT NULL, 
	approved_by VARCHAR(100), 
	submission_reference VARCHAR(60), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_regulatory_reports_report_type ON regulatory_reports (report_type);
CREATE INDEX IF NOT EXISTS ix_regulatory_reports_status ON regulatory_reports (status);

CREATE TABLE IF NOT EXISTS sars (
	id SERIAL NOT NULL, 
	reference VARCHAR(30) NOT NULL, 
	subject_type VARCHAR(20) NOT NULL, 
	subject_id INTEGER NOT NULL, 
	subject_name VARCHAR(250) NOT NULL, 
	customer_id INTEGER, 
	alert_id INTEGER, 
	status VARCHAR(20) NOT NULL, 
	typologies JSONB NOT NULL, 
	evidence JSONB NOT NULL, 
	narrative TEXT NOT NULL, 
	engine VARCHAR(30) NOT NULL, 
	total_amount_eur FLOAT NOT NULL, 
	prepared_by VARCHAR(100) NOT NULL, 
	approved_by VARCHAR(100), 
	mlro_note TEXT, 
	filing_reference VARCHAR(60), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	decided_at TIMESTAMP WITH TIME ZONE, 
	filed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (reference)
);

CREATE INDEX IF NOT EXISTS ix_sars_customer_id ON sars (customer_id);
CREATE INDEX IF NOT EXISTS ix_sars_status ON sars (status);

CREATE TABLE IF NOT EXISTS travel_rule_transfers (
	id SERIAL NOT NULL, 
	customer_id INTEGER, 
	corporate_id INTEGER, 
	wallet_id INTEGER, 
	direction VARCHAR(3) NOT NULL, 
	tx_hash VARCHAR(80), 
	asset VARCHAR(10) NOT NULL, 
	amount_eur FLOAT NOT NULL, 
	originator JSONB NOT NULL, 
	beneficiary JSONB NOT NULL, 
	counterparty_vasp VARCHAR(150), 
	self_hosted BOOLEAN NOT NULL, 
	ownership_proof BOOLEAN NOT NULL, 
	checks JSONB NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	reasons JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_travel_rule_transfers_customer_id ON travel_rule_transfers (customer_id);
CREATE INDEX IF NOT EXISTS ix_travel_rule_transfers_status ON travel_rule_transfers (status);

CREATE TABLE IF NOT EXISTS users (
	id SERIAL NOT NULL, 
	username VARCHAR(60) NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	role VARCHAR(25) NOT NULL, 
	email VARCHAR(160) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);

CREATE TABLE IF NOT EXISTS assessments (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	agent VARCHAR(30) NOT NULL, 
	engine VARCHAR(30) NOT NULL, 
	output JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_assessments_customer_agent ON assessments (customer_id, agent);

CREATE TABLE IF NOT EXISTS case_notes (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	engine VARCHAR(30) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_case_notes_customer_id ON case_notes (customer_id);

CREATE TABLE IF NOT EXISTS documents (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	doc_type VARCHAR(40) NOT NULL, 
	description VARCHAR(300), 
	issued_date DATE, 
	expiry_date DATE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_documents_customer_id ON documents (customer_id);

CREATE TABLE IF NOT EXISTS ownership_edges (
	id SERIAL NOT NULL, 
	corporate_id INTEGER NOT NULL, 
	owner_key VARCHAR(60) NOT NULL, 
	owned_key VARCHAR(60) NOT NULL, 
	percentage FLOAT NOT NULL, 
	control_type VARCHAR(20) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(corporate_id) REFERENCES corporates (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ownership_edges_corporate_id ON ownership_edges (corporate_id);

CREATE TABLE IF NOT EXISTS ownership_nodes (
	id SERIAL NOT NULL, 
	corporate_id INTEGER NOT NULL, 
	node_key VARCHAR(60) NOT NULL, 
	name VARCHAR(250) NOT NULL, 
	node_type VARCHAR(10) NOT NULL, 
	country VARCHAR(100), 
	dob DATE, 
	role VARCHAR(60), 
	id_verified BOOLEAN NOT NULL, 
	verification_note VARCHAR(300), 
	is_listed BOOLEAN NOT NULL, 
	is_trust BOOLEAN NOT NULL, 
	is_nominee BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(corporate_id) REFERENCES corporates (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_nodes_corp_key ON ownership_nodes (corporate_id, node_key);

CREATE TABLE IF NOT EXISTS reviews (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	review_type VARCHAR(20) NOT NULL, 
	trigger VARCHAR(60) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	recommendation VARCHAR(80), 
	outcome JSONB NOT NULL, 
	decision VARCHAR(40), 
	decision_note TEXT, 
	decided_by VARCHAR(100), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_reviews_customer_id ON reviews (customer_id);
CREATE INDEX IF NOT EXISTS ix_reviews_status ON reviews (status);

CREATE TABLE IF NOT EXISTS screening_hits (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	list_type VARCHAR(20) NOT NULL, 
	entity_id VARCHAR(60) NOT NULL, 
	matched_name VARCHAR(200) NOT NULL, 
	confidence FLOAT NOT NULL, 
	details JSONB NOT NULL, 
	disposition VARCHAR(20) NOT NULL, 
	disposition_note TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_hits_customer_list_entity ON screening_hits (customer_id, list_type, entity_id);

CREATE TABLE IF NOT EXISTS transactions (
	id SERIAL NOT NULL, 
	txn_ref VARCHAR(30) NOT NULL, 
	customer_id INTEGER, 
	corporate_id INTEGER, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	direction VARCHAR(3) NOT NULL, 
	amount_eur FLOAT NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	channel VARCHAR(15) NOT NULL, 
	counterparty VARCHAR(160) NOT NULL, 
	counterparty_country VARCHAR(60) NOT NULL, 
	flags JSONB NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (txn_ref), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(corporate_id) REFERENCES corporates (id)
);

CREATE INDEX IF NOT EXISTS ix_transactions_ts ON transactions (ts);
CREATE INDEX IF NOT EXISTS ix_txn_customer_ts ON transactions (customer_id, ts);

CREATE TABLE IF NOT EXISTS wallets (
	id SERIAL NOT NULL, 
	address VARCHAR(100) NOT NULL, 
	chain VARCHAR(10) NOT NULL, 
	label VARCHAR(200), 
	customer_id INTEGER, 
	corporate_id INTEGER, 
	hosted_by_vasp VARCHAR(150), 
	self_hosted BOOLEAN NOT NULL, 
	risk_score INTEGER, 
	risk_level VARCHAR(10), 
	last_screened_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL, 
	FOREIGN KEY(corporate_id) REFERENCES corporates (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_wallet_chain_addr ON wallets (chain, address);
CREATE INDEX IF NOT EXISTS ix_wallets_corporate_id ON wallets (corporate_id);
CREATE INDEX IF NOT EXISTS ix_wallets_customer_id ON wallets (customer_id);
