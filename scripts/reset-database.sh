#!/bin/bash
# Database Reset Script for Nutanix PXE/Config Server
# Provides options to clear database entries or reset the entire database

set -euo pipefail

# Configuration - default values can be overridden by environment variables
DB_USER="${DB_USER:-nutanix}"
DB_PASSWORD="${DB_PASSWORD:-nutanix}"
DB_NAME="${DB_NAME:-nutanix_pxe}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
log_info() { echo -e "${BLUE}ℹ INFO${NC}: $1"; }
log_success() { echo -e "${GREEN}✓ SUCCESS${NC}: $1"; }
log_warning() { echo -e "${YELLOW}⚠ WARNING${NC}: $1"; }
log_error() { echo -e "${RED}✗ ERROR${NC}: $1"; }

# Function to display usage
usage() {
    cat << EOF
Nutanix PXE Server Database Reset Tool

Usage: $0 [OPTIONS]

Options:
    --clear-data    Clear all data from tables (keeps schema)
    --drop-create   Drop and recreate the database
    --help, -h      Show this help message

Environment Variables:
    DB_USER         Database user (default: nutanix)
    DB_PASSWORD     Database password (default: nutanix)
    DB_NAME         Database name (default: nutanix_pxe)
    DB_HOST         Database host (default: localhost)
    DB_PORT         Database port (default: 5432)

Examples:
    $0 --clear-data
    $0 --drop-create
    DB_USER=admin DB_PASSWORD=secret $0 --clear-data

EOF
}

# Function to check if PostgreSQL client is available
check_dependencies() {
    if ! command -v psql >/dev/null 2>&1; then
        log_error "PostgreSQL client (psql) not found"
        log_error "Please install PostgreSQL client tools:"
        log_error "  Ubuntu/Debian: sudo apt-get install postgresql-client"
        log_error "  CentOS/RHEL: sudo yum install postgresql"
        log_error "  macOS: brew install postgresql"
        exit 1
    fi
}

# Function to test database connection
test_connection() {
    log_info "Testing database connection..."
    
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" >/dev/null 2>&1; then
        log_success "Database connection successful"
        return 0
    else
        log_error "Cannot connect to database"
        log_error "Please check:"
        log_error "1. Database server is running"
        log_error "2. Connection parameters are correct"
        log_error "3. Database user has proper permissions"
        return 1
    fi
}

# Function to clear all data from tables
clear_data() {
    log_warning "This will DELETE ALL DATA from the database!"
    read -p "Are you sure you want to continue? (type 'yes' to confirm): " confirmation
    
    if [[ "$confirmation" != "yes" ]]; then
        log_info "Operation cancelled"
        exit 0
    fi
    
    log_info "Clearing all data from tables..."
    
    # SQL commands to truncate all tables
    local sql_commands="
        TRUNCATE TABLE deployment_history RESTART IDENTITY CASCADE;
        TRUNCATE TABLE ip_reservations RESTART IDENTITY CASCADE;
        TRUNCATE TABLE dns_records RESTART IDENTITY CASCADE;
        TRUNCATE TABLE vnic_info RESTART IDENTITY CASCADE;
        TRUNCATE TABLE clusters RESTART IDENTITY CASCADE;
        TRUNCATE TABLE nodes RESTART IDENTITY CASCADE;
    "
    
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "$sql_commands"; then
        log_success "All data cleared successfully"
    else
        log_error "Failed to clear data"
        exit 1
    fi
}

# Function to drop and recreate database
drop_create_database() {
    log_warning "This will DROP and RECREATE the entire database!"
    log_warning "ALL DATA will be permanently lost!"
    read -p "Are you sure you want to continue? (type 'yes' to confirm): " confirmation
    
    if [[ "$confirmation" != "yes" ]]; then
        log_info "Operation cancelled"
        exit 0
    fi
    
    log_info "Dropping database $DB_NAME..."
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"; then
        log_success "Database dropped"
    else
        log_error "Failed to drop database"
        exit 1
    fi
    
    log_info "Creating database $DB_NAME..."
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME WITH OWNER = $DB_USER;"; then
        log_success "Database created"
    else
        log_error "Failed to create database"
        exit 1
    fi
    
    log_info "Database reset completed successfully"
    log_info "The application will recreate tables on next startup"
}

# Main function
main() {
    # Check dependencies
    check_dependencies
    
    # Parse command line arguments
    case "${1:-}" in
        "--clear-data")
            test_connection
            clear_data
            ;;
        "--drop-create")
            test_connection
            drop_create_database
            ;;
        "--help"|"-h")
            usage
            ;;
        "")
            usage
            exit 1
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"