-- Create portal_users table
CREATE TABLE IF NOT EXISTS portal_users (
    id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Add foreign key constraint to conversations table if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_conversations_portal_user_id'
    ) THEN
        ALTER TABLE conversations 
        ADD CONSTRAINT fk_conversations_portal_user_id 
        FOREIGN KEY (portal_user_id) 
        REFERENCES portal_users (id);
    END IF;
END $$; 