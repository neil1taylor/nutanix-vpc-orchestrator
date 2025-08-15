# Changes Required for Nutanix CE Deployment on IBM Cloud VPC

This document outlines the necessary modifications to the codebase to implement the Nutanix CE deployment process on IBM Cloud VPC bare metal servers as described in `docs/ce_deploy_on_vpc.md`.

## 1. Modify `setup.sh`

**Action:** Add the `build_initrd-vpc()` function to the `setup.sh` script.
**Details:** This function is responsible for creating a custom initrd image that includes the Ionic NIC driver and the `vpc_init` script. The complete implementation is available in the task context.

## 2. Modify `boot_service.py`

**Action:** Update `boot_service.py` to align with the specific iPXE script and simplify boot handling.

**Details:**
*   **Update `generate_boot_script`:** Modify this method to use the iPXE script template provided in `docs/ce_deploy_on_vpc.md`. This script uses `initrd ${{base-url}}/boot/images/initrd-vpc.img` and `kernel ${{base-url}}/kernel init=/vpc_init ...`.
*   **Remove `generate_iso_boot_script`:** Delete this method entirely.
*   **Remove `generate_default_boot_script`:** Delete this method entirely.
*   **Modify `handle_ipxe_boot`:** Remove the conditional logic that calls `generate_iso_boot_script` and `generate_default_boot_script`. Ensure it only calls `generate_boot_script` for all iPXE boot requests. abd remove the functions `generate_iso_boot_script` and `generate_default_boot_script`.

## 3. Verify `vpc_init` and `vpc_ce_installation.py`

**Action:** Ensure these scripts exist in the project root.
**Status:** Confirmed that both `vpc_init` and `vpc_ce_installation.py` exist. No changes needed for their existence.

## 4. Verify `config.py`, `ibm_cloud_client.py`, `server_profiles.py`, `node_provisioner.py`

**Action:** Ensure these files correctly provide configuration, interact with IBM Cloud APIs, define server profiles, and handle provisioning/monitoring.
**Status:** Based on the review, these files appear to be correctly implemented and integrated. No changes are immediately required in these files for the core functionality described in `docs/ce_deploy_on_vpc.md`.

## Summary of Changes

The primary changes required are:
1.  Adding the `build_initrd-vpc` function to `setup.sh`.
2.  Modifying `boot_service.py` to update `generate_boot_script`, remove unused script generation methods, and simplify `handle_ipxe_boot`.