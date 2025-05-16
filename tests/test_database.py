#!/usr/bin/env python3
import unittest
import pytest
import os
import subprocess
import json
import psycopg2
from psycopg2 import sql

def run_sql(query):
    """Run SQL query in the postgres container"""
    result = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.dev.yml", "exec", "-T", "postgres", 
            "psql", "-U", "admin", "-d", "chatwithoats", "-t", "-c", query],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()

@pytest.mark.database
class DatabaseTest(unittest.TestCase):
    """
    Database tests for ChatWithOats backend.
    
    These tests verify that the database connection works and that
    required tables exist.
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
            'messages'  # Instead of chat_messages
        ]
        
        tables_json = run_sql("""
            SELECT json_agg(table_name) 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE';
        """)
        
        # Strip any whitespace and extract the JSON array
        tables_json = tables_json.strip()
        
        # The command might return brackets on separate lines, fix that
        if not tables_json.startswith('['):
            tables_json = tables_json.replace('\n', '')
            # Find the first [ and last ]
            start = tables_json.find('[')
            end = tables_json.rfind(']') + 1
            if start >= 0 and end > start:
                tables_json = tables_json[start:end]
        
        try:
            existing_tables = json.loads(tables_json)
        except json.JSONDecodeError:
            self.fail(f"Failed to parse tables JSON: {tables_json}")
            
        # Convert to lowercase for case-insensitive comparison
        existing_tables = [t.lower() for t in existing_tables if t]
        
        for table in required_tables:
            self.assertIn(table.lower(), existing_tables, f"Required table '{table}' does not exist")
        
        print(f"✓ All required tables exist: {', '.join(required_tables)}")
    
    def test_03_key_tables_columns(self):
        """Test that key tables have expected columns"""
        table_columns = {
            'chat_settings': ['id', 'name', 'description', 'system_prompt'],
            'conversations': ['chatid', 'name', 'is_group', 'chat_settings_id'],
            'tools': ['id', 'name', 'description', 'type', 'configuration'],
            'messages': ['id', 'chatid', 'content', 'role']
        }
        
        for table, expected_columns in table_columns.items():
            columns_json = run_sql(f"""
                SELECT json_agg(column_name)
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = '{table}';
            """)
            
            # Clean up the JSON
            columns_json = columns_json.strip()
            if not columns_json.startswith('['):
                columns_json = columns_json.replace('\n', '')
                start = columns_json.find('[')
                end = columns_json.rfind(']') + 1
                if start >= 0 and end > start:
                    columns_json = columns_json[start:end]
            
            try:
                existing_columns = json.loads(columns_json)
            except json.JSONDecodeError:
                self.fail(f"Failed to parse columns JSON for {table}: {columns_json}")
                
            # Convert to lowercase for case-insensitive comparison
            existing_columns = [c.lower() for c in existing_columns if c]
            
            for column in expected_columns:
                self.assertIn(column.lower(), existing_columns, 
                             f"Required column '{column}' not found in table '{table}'")
            
            print(f"✓ Table '{table}' has all required columns: {', '.join(expected_columns)}")

if __name__ == "__main__":
    unittest.main() 