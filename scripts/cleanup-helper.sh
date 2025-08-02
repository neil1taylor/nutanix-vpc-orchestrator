#!/bin/bash
# Cleanup Helper Script for Nutanix PXE/Config Server
# Provides easy access to cleanup operations

set -euo pipefail

# Configuration
PXE_SERVER="${PXE_SERVER:-localhost:8080}"
API_BASE="http://${PXE_SERVER}/api/cleanup"

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
Nutanix PXE Server Cleanup Helper

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    status                          Show overall cleanup status
    status-node <node_name>         Show cleanup status for specific node
    status-deployment <id>          Show cleanup status for deployment
    
    cleanup-node <node_id>          Clean up resources for a specific node
    cleanup-deployment <id>         Clean up all resources for a deployment
    cleanup-orphaned [hours]        Clean up orphaned resources (default: 24h)
    
    validate <node_id>              Validate cleanup completion for a node
    
    script <deployment_id>          Generate cleanup script for deployment
    
    batch-nodes <node1,node2,...>   Batch cleanup multiple nodes
    batch-validate <node1,node2>    Batch validate multiple nodes

Examples:
    $0 status
    $0 cleanup-node 1
    $0 cleanup-deployment nutanix-poc-bm-node-01
    $0 validate 1
    $0 script deployment-123
    $0 cleanup-orphaned 48
    $0 batch-nodes node1,node2,node3

Environment Variables:
    PXE_SERVER                      PXE server address (default: localhost:8080)

EOF
}

# Function to make API calls
api_call() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"
    
    local curl_args=("-s" "-w" "\n%{http_code}")
    
    if [[ "$method" == "POST" ]]; then
        curl_args+=("-X" "POST")
        if [[ -n "$data" ]]; then
            curl_args+=("-H" "Content-Type: application/json" "-d" "$data")
        fi
    fi
    
    local response
    response=$(curl "${curl_args[@]}" "${API_BASE}${endpoint}")
    
    local http_code
    http_code=$(echo "$response" | tail -n1)
    local body
    body=$(echo "$response" | sed '$d')
    
    if [[ "$http_code" -ge 200 && "$http_code" -lt 300 ]]; then
        echo "$body"
        return 0
    else
        log_error "API call failed with HTTP $http_code"
        echo "$body" | jq -r '.error // .message // "Unknown error"' 2>/dev/null || echo "$body"
        return 1
    fi
}

# Function to format JSON output
format_json() {
    if command -v jq >/dev/null 2>&1; then
        jq -C '.'
    else
        cat
    fi
}

# Function to show cleanup status
show_status() {
    local node_name="${1:-}"
    local deployment_id="${2:-}"
    
    log_info "Fetching cleanup status..."
    
    local endpoint="/status"
    local params=""
    
    if [[ -n "$node_name" ]]; then
        params="?node_name=$node_name"
    elif [[ -n "$deployment_id" ]]; then
        params="?deployment_id=$deployment_id"
    fi
    
    if api_call "GET" "${endpoint}${params}"; then
        log_success "Status retrieved successfully"
    fi
}

# Function to cleanup a node
cleanup_node() {
    local node_id="$1"
    
    log_info "Starting cleanup for node $node_id..."
    
    if response=$(api_call "POST" "/node/$node_id"); then
        log_success "Node cleanup initiated"
        
        # Extract summary information
        if command -v jq >/dev/null 2>&1; then
            local total_ops
            total_ops=$(echo "$response" | jq -r '.summary.total_operations // 0')
            local successful_ops
            successful_ops=$(echo "$response" | jq -r '.summary.successful_operations // 0')
            local success_rate
            success_rate=$(echo "$response" | jq -r '.summary.success_rate // "0%"')
            
            log_info "Cleanup Summary: $successful_ops/$total_ops operations successful ($success_rate)"
        fi
        
        echo "$response" | format_json
    else
        log_error "Node cleanup failed"
        return 1
    fi
}

# Function to cleanup a deployment
cleanup_deployment() {
    local deployment_id="$1"
    
    log_info "Starting cleanup for deployment $deployment_id..."
    
    if response=$(api_call "POST" "/deployment/$deployment_id"); then
        log_success "Deployment cleanup initiated"
        
        # Extract summary information
        if command -v jq >/dev/null 2>&1; then
            local nodes_cleaned
            nodes_cleaned=$(echo "$response" | jq -r '.nodes_cleaned // 0')
            log_info "Nodes cleaned: $nodes_cleaned"
        fi
        
        echo "$response" | format_json
    else
        log_error "Deployment cleanup failed"
        return 1
    fi
}

# Function to cleanup orphaned resources
cleanup_orphaned() {
    local max_age_hours="${1:-24}"
    
    log_info "Starting cleanup of orphaned resources (older than ${max_age_hours}h)..."
    
    local data
    data=$(jq -n --arg hours "$max_age_hours" '{max_age_hours: ($hours | tonumber)}')
    
    if response=$(api_call "POST" "/orphaned" "$data"); then
        log_success "Orphaned resource cleanup initiated"
        
        # Extract summary information
        if command -v jq >/dev/null 2>&1; then
            local nodes_cleaned
            nodes_cleaned=$(echo "$response" | jq -r '.orphaned_nodes_cleaned // 0')
            log_info "Orphaned nodes cleaned: $nodes_cleaned"
        fi
        
        echo "$response" | format_json
    else
        log_error "Orphaned resource cleanup failed"
        return 1
    fi
}

# Function to validate cleanup
validate_cleanup() {
    local node_id="$1"
    
    log_info "Validating cleanup for node $node_id..."
    
    if response=$(api_call "GET" "/validate/$node_id"); then
        # Check if cleanup is complete
        if command -v jq >/dev/null 2>&1; then
            local cleanup_complete
            cleanup_complete=$(echo "$response" | jq -r '.cleanup_complete // false')
            
            if [[ "$cleanup_complete" == "true" ]]; then
                log_success "Cleanup validation passed"
            else
                log_warning "Cleanup validation found issues"
                
                # Show validation details
                echo "$response" | jq -r '.validation_results[]? | "  \(.check): \(.status) - \(.message)"' 2>/dev/null || true
            fi
        fi
        
        echo "$response" | format_json
    else
        log_error "Cleanup validation failed"
        return 1
    fi
}

# Function to generate cleanup script
generate_script() {
    local deployment_id="$1"
    local output_file="${2:-cleanup-${deployment_id}.sh}"
    
    log_info "Generating cleanup script for deployment $deployment_id..."
    
    if curl -s -f "${API_BASE}/script/$deployment_id" -o "$output_file"; then
        chmod +x "$output_file"
        log_success "Cleanup script saved to $output_file"
        log_info "Execute with: ./$output_file"
    else
        log_error "Failed to generate cleanup script"
        return 1
    fi
}

# Function to perform batch operations
batch_cleanup_nodes() {
    local nodes="$1"
    
    log_info "Starting batch cleanup for nodes: $nodes"
    
    # Convert comma-separated list to JSON array
    local nodes_array
    nodes_array=$(echo "$nodes" | tr ',' '\n' | jq -R . | jq -s .)
    
    local data
    data=$(jq -n --argjson targets "$nodes_array" '{operation: "cleanup_nodes", targets: $targets}')
    
    if response=$(api_call "POST" "/batch" "$data"); then
        # Extract summary information
        if command -v jq >/dev/null 2>&1; then
            local total_ops
            total_ops=$(echo "$response" | jq -r '.total_operations // 0')
            local successful_ops
            successful_ops=$(echo "$response" | jq -r '.successful_operations // 0')
            local success_rate
            success_rate=$(echo "$response" | jq -r '.success_rate // "0%"')
            
            log_info "Batch cleanup completed: $successful_ops/$total_ops operations successful ($success_rate)"
        fi
        
        echo "$response" | format_json
    else
        log_error "Batch cleanup failed"
        return 1
    fi
}

# Function to perform batch validation
batch_validate() {
    local nodes="$1"
    
    log_info "Starting batch validation for nodes: $nodes"
    
    # Convert comma-separated list to JSON array
    local nodes_array
    nodes_array=$(echo "$nodes" | tr ',' '\n' | jq -R . | jq -s .)
    
    local data
    data=$(jq -n --argjson targets "$nodes_array" '{operation: "validate_cleanup", targets: $targets}')
    
    if response=$(api_call "POST" "/batch" "$data"); then
        # Show validation summary
        if command -v jq >/dev/null 2>&1; then
            local total_nodes
            total_nodes=$(echo "$response" | jq -r '.total_operations // 0')
            local clean_nodes
            clean_nodes=$(echo "$response" | jq '[.results[] | select(.cleanup_complete == true)] | length')
            
            log_info "Batch validation completed: $clean_nodes/$total_nodes nodes fully cleaned"
            
            # Show details for each node
            echo "$response" | jq -r '.results[] | "\(.node_name): \(if .cleanup_complete then "✓ CLEAN" else "✗ ISSUES" end)"'
        fi
        
        echo "$response" | format_json
    else
        log_error "Batch validation failed"
        return 1
    fi
}

# Function to show interactive cleanup menu
interactive_menu() {
    while true; do
        echo
        echo "=== Nutanix PXE Server Cleanup Menu ==="
        echo "1. Show overall status"
        echo "2. Show node status"
        echo "3. Show deployment status"
        echo "4. Cleanup specific node"
        echo "5. Cleanup deployment"
        echo "6. Cleanup orphaned resources"
        echo "7. Validate node cleanup"
        echo "8. Generate cleanup script"
        echo "9. Batch cleanup nodes"
        echo "10. Batch validate nodes"
        echo "0. Exit"
        echo
        
        read -p "Select option [0-10]: " choice
        
        case $choice in
            1)
                show_status
                ;;
            2)
                read -p "Enter node name: " node_name
                show_status "$node_name"
                ;;
            3)
                read -p "Enter deployment ID: " deployment_id
                show_status "" "$deployment_id"
                ;;
            4)
                read -p "Enter node ID: " node_id
                cleanup_node "$node_id"
                ;;
            5)
                read -p "Enter deployment ID: " deployment_id
                cleanup_deployment "$deployment_id"
                ;;
            6)
                read -p "Enter max age in hours [24]: " max_age
                max_age=${max_age:-24}
                cleanup_orphaned "$max_age"
                ;;
            7)
                read -p "Enter node ID: " node_id
                validate_cleanup "$node_id"
                ;;
            8)
                read -p "Enter deployment ID: " deployment_id
                read -p "Enter output filename [cleanup-${deployment_id}.sh]: " filename
                filename=${filename:-"cleanup-${deployment_id}.sh"}
                generate_script "$deployment_id" "$filename"
                ;;
            9)
                read -p "Enter comma-separated node names: " nodes
                batch_cleanup_nodes "$nodes"
                ;;
            10)
                read -p "Enter comma-separated node names: " nodes
                batch_validate "$nodes"
                ;;
            0)
                log_info "Exiting..."
                exit 0
                ;;
            *)
                log_error "Invalid option. Please select 0-10."
                ;;
        esac
        
        echo
        read -p "Press Enter to continue..."
    done
}

# Function to check dependencies
check_dependencies() {
    local missing_deps=()
    
    if ! command -v curl >/dev/null 2>&1; then
        missing_deps+=("curl")
    fi
    
    if ! command -v jq >/dev/null 2>&1; then
        log_warning "jq not found - JSON output will not be formatted"
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing required dependencies: ${missing_deps[*]}"
        log_error "Please install the missing dependencies and try again"
        exit 1
    fi
}

# Function to test connectivity
test_connectivity() {
    log_info "Testing connectivity to PXE server: $PXE_SERVER"
    
    if curl -s -f --max-time 10 "http://${PXE_SERVER}/health" >/dev/null; then
        log_success "PXE server is reachable"
        return 0
    else
        log_error "Cannot reach PXE server at $PXE_SERVER"
        log_error "Please check:"
        log_error "1. Server is running"
        log_error "2. Network connectivity"
        log_error "3. PXE_SERVER environment variable"
        return 1
    fi
}

# Main script logic
main() {
    # Check dependencies
    check_dependencies
    
    # Show banner
    echo "=== Nutanix PXE Server Cleanup Helper ==="
    echo "Server: $PXE_SERVER"
    echo
    
    # Test connectivity
    if ! test_connectivity; then
        exit 1
    fi
    
    # Parse command line arguments
    case "${1:-}" in
        "status")
            show_status
            ;;
        "status-node")
            if [[ -z "${2:-}" ]]; then
                log_error "Node name required"
                usage
                exit 1
            fi
            show_status "$2"
            ;;
        "status-deployment")
            if [[ -z "${2:-}" ]]; then
                log_error "Deployment ID required"
                usage
                exit 1
            fi
            show_status "" "$2"
            ;;
        "cleanup-node")
            if [[ -z "${2:-}" ]]; then
                log_error "Node ID required"
                usage
                exit 1
            fi
            cleanup_node "$2"
            ;;
        "cleanup-deployment")
            if [[ -z "${2:-}" ]]; then
                log_error "Deployment ID required"
                usage
                exit 1
            fi
            cleanup_deployment "$2"
            ;;
        "cleanup-orphaned")
            max_age="${2:-24}"
            cleanup_orphaned "$max_age"
            ;;
        "validate")
            if [[ -z "${2:-}" ]]; then
                log_error "Node ID required"
                usage
                exit 1
            fi
            validate_cleanup "$2"
            ;;
        "script")
            if [[ -z "${2:-}" ]]; then
                log_error "Deployment ID required"
                usage
                exit 1
            fi
            output_file="${3:-}"
            if [[ -n "$output_file" ]]; then
                generate_script "$2" "$output_file"
            else
                generate_script "$2"
            fi
            ;;
        "batch-nodes")
            if [[ -z "${2:-}" ]]; then
                log_error "Comma-separated node names required"
                usage
                exit 1
            fi
            batch_cleanup_nodes "$2"
            ;;
        "batch-validate")
            if [[ -z "${2:-}" ]]; then
                log_error "Comma-separated node names required"
                usage
                exit 1
            fi
            batch_validate "$2"
            ;;
        "interactive"|"")
            interactive_menu
            ;;
        "help"|"--help"|"-h")
            usage
            ;;
        *)
            log_error "Unknown command: $1"
            usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"