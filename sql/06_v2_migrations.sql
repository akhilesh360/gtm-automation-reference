-- v2 additive migrations for databases created by v1. Safe to run repeatedly.
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS approver VARCHAR;
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS decision_at TIMESTAMP;
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR;
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS erp_order_id VARCHAR;
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS erp_status VARCHAR DEFAULT 'Not Sent';
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS erp_sent_at TIMESTAMP;
