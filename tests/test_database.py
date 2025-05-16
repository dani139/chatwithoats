#!/usr/bin/env python3
import unittest
import subprocess
import json
import os
import pytest

# Get the project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCKER_COMPOSE_FILE = os.path.join(PROJECT_ROOT, "docker-compose.dev.yml")

def run_sql(query):
    """Run a SQL query and return the result"""
    result = subprocess.run(
        ["docker", "compose", "-f", DOCKER_COMPOSE_FILE, "exec", "-T", "postgres", 
         "psql", "-U", "admin", "-d", "chatwithoats", "-t", "-c", query],
        check=True,
        text=True,
        capture_output=True
    )
    return result.stdout.strip()

@pytest.mark.database
class DatabaseTest(unittest.TestCase):
    """
    Database tests for ChatWithOats backend.
    
    These tests verify:
    1. Database connectivity
    2. Table existence and structure
    3. Schema correctness
    """
    
    def test_01_database_connection(self):
        """Test basic database connection"""
        result = run_sql("SELECT 'DB Connection Test' AS result;")
        self.assertIn("DB Connection Test", result, "Database connection failed")
        
        print("✓ Database connection successful")
    
    def test_02_required_tables_exist(self):
        """Test that required tables exist in the database"""
        required_tables = [
            'portal_users',
            'chat_settings',
            'conversations',
            'tools',
            'messages',  # Instead of chat_messages
            'apis',
            'api_requests',
            'chat_settings_tools'
        ]
        
        tables_json = run_sql("""
            SELECT json_agg(table_name)
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE';
        """)
        
        # Parse JSON result
        tables = json.loads(tables_json)
        
        # Check if all required tables exist
        for table in required_tables:
            self.assertIn(table, tables, f"Required table '{table}' not found in database")
        
        print(f"✓ All {len(required_tables)} required tables exist")
    
    def test_03_key_tables_columns(self):
        """Test that key tables have expected columns"""
        table_columns = {
            'chat_settings': ['id', 'name', 'description', 'system_prompt', 'model'],
            'conversations': ['chatid', 'name', 'is_group', 'chat_settings_id', 'source_type'],
            'tools': ['id', 'name', 'description', 'type', 'tool_type', 'api_request_id', 'function_schema', 'configuration'],
            'messages': ['id', 'chatid', 'content', 'role', 'sender', 'type']
        }
        
        for table, expected_columns in table_columns.items():
            columns_json = run_sql(f"""
                SELECT json_agg(column_name)
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = '{table}';
            """)
            
            # Parse JSON result
            columns = json.loads(columns_json)
            
            # Check if all expected columns exist
            for col in expected_columns:
                self.assertIn(col, columns, f"Expected column '{col}' not found in table '{table}'")
            
            print(f"✓ Table '{table}' has all expected columns")
    
    def test_04_check_tools_columns(self):
        """Test that the tools table has the correct structure"""
        # Get the tool_type column
        column_info = run_sql("""
            SELECT 
                column_name, 
                data_type, 
                is_nullable
            FROM 
                information_schema.columns
            WHERE 
                table_schema = 'public'
                AND table_name = 'tools'
                AND column_name = 'tool_type';
        """)
        
        # Check that the tool_type column exists
        self.assertIn("tool_type", column_info, "tools table missing tool_type column")
        
        # Get the api_request_id column
        column_info = run_sql("""
            SELECT 
                column_name, 
                data_type, 
                is_nullable
            FROM 
                information_schema.columns
            WHERE 
                table_schema = 'public'
                AND table_name = 'tools'
                AND column_name = 'api_request_id';
        """)
        
        # Check that the api_request_id column exists
        self.assertIn("api_request_id", column_info, "tools table missing api_request_id column")
        
        print("✓ Tools table has correct structure")

if __name__ == "__main__":
    unittest.main() 