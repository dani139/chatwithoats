-- Remove user_id and is_default columns from chat_settings table

-- First, drop any existing foreign keys that reference user_id
ALTER TABLE chat_settings DROP CONSTRAINT IF EXISTS fk_chat_settings_user_id;

-- Then, remove the columns
ALTER TABLE chat_settings DROP COLUMN IF EXISTS user_id;
ALTER TABLE chat_settings DROP COLUMN IF EXISTS is_default;

-- Drop the related indexes
DROP INDEX IF EXISTS idx_chat_settings_user_id; 