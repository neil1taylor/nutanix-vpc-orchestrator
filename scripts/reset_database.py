#!/usr/bin/env python3
"""
Database Reset Script for Nutanix PXE/Config Server
Provides programmatic way to clear database entries
"""

import os
import sys
import psycopg2
from psycopg2 import sql

# Configuration - default values can be overridden by environment variables
DB_USER = os.environ.get('DB_USER', 'nutanix')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'nutanix')
DB_NAME = os.environ.get('DB_NAME', 'nutanix_pxe')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')

def get_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def clear_data():
    """Clear all data from tables while keeping schema"""
    print("⚠ WARNING: This will DELETE ALL DATA from the database!")
    confirmation = input("Are you sure you want to continue? (type 'yes' to confirm): ")
    
    if confirmation != 'yes':
        print("Operation cancelled")
        return False
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Truncate all tables in correct order to avoid foreign key constraints
                tables = [
                    'deployment_history',
                    'ip_reservations',
                    'dns_records',
                    'vnic_info',
                    'clusters',
                    'nodes'
                ]
                
                for table in tables:
                    cur.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                        sql.Identifier(table)
                    ))
                    print(f"✓ Cleared table: {table}")
                
                conn.commit()
                print("✓ All data cleared successfully")
                return True
                
    except Exception as e:
        print(f"✗ Error clearing data: {e}")
        return False

def drop_create_database():
    """Drop and recreate the database"""
    print("⚠ WARNING: This will DROP and RECREATE the entire database!")
    print("⚠ ALL DATA will be permanently lost!")
    confirmation = input("Are you sure you want to continue? (type 'yes' to confirm): ")
    
    if confirmation != 'yes':
        print("Operation cancelled")
        return False
    
    try:
        # Connect to postgres database to drop/create
        with psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database='postgres',
            user=DB_USER,
            password=DB_PASSWORD
        ) as conn:
            with conn.cursor() as cur:
                # Terminate all connections to the target database
                cur.execute("""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                """, (DB_NAME,))
                
                # Drop database
                cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(DB_NAME)
                ))
                print(f"✓ Database {DB_NAME} dropped")
                
                # Create database
                cur.execute(sql.SQL("CREATE DATABASE {} WITH OWNER = %s").format(
                    sql.Identifier(DB_NAME)
                ), (DB_USER,))
                print(f"✓ Database {DB_NAME} created")
                
        print("✓ Database reset completed successfully")
        print("The application will recreate tables on next startup")
        return True
        
    except Exception as e:
        print(f"✗ Error resetting database: {e}")
        return False

def test_connection():
    """Test database connection"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                print("✓ Database connection successful")
                return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False

def show_usage():
    """Show usage information"""
    print("""
Nutanix PXE Server Database Reset Tool

Usage: python reset_database.py [OPTIONS]

Options:
    --clear-data    Clear all data from tables (keeps schema)
    --drop-create   Drop and recreate the database
    --test          Test database connection
    --help, -h      Show this help message

Environment Variables:
    DB_USER         Database user (default: nutanix)
    DB_PASSWORD     Database password (default: nutanix)
    DB_NAME         Database name (default: nutanix_pxe)
    DB_HOST         Database host (default: localhost)
    DB_PORT         Database port (default: 5432)

Examples:
    python reset_database.py --clear-data
    python reset_database.py --drop-create
    DB_USER=admin DB_PASSWORD=secret python reset_database.py --clear-data
    """)

def main():
    """Main function"""
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(1)
    
    option = sys.argv[1]
    
    if option in ['--help', '-h']:
        show_usage()
        sys.exit(0)
    elif option == '--test':
        if test_connection():
            sys.exit(0)
        else:
            sys.exit(1)
    elif option == '--clear-data':
        if not test_connection():
            sys.exit(1)
        if clear_data():
            sys.exit(0)
        else:
            sys.exit(1)
    elif option == '--drop-create':
        if not test_connection():
            sys.exit(1)
        if drop_create_database():
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        print(f"Unknown option: {option}")
        show_usage()
        sys.exit(1)

if __name__ == '__main__':
    main()