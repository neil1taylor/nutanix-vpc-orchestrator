# Troublshooting

## Run the setup script

`setup.sh` is run during the cloud-int stage via `deploy.sh` but can be run again and the output seen on the console as well as `/var/log/nutanix-pxe-setup.log`. When run subsequent times, some things, like the database user, will fail as they have already been configured.

1. SSH to the pxe server

`ssh -i ~/.ssh/nutanix-ce-poc root@150.240.65.231`

```bash
rm -rf /var/log/nutanix-pxe
cd /
GITHUB_REPO="https://github.com/neil1taylor/nutanix-vpc-orchestrator"
GITHUB_BRANCH="main"
PROJECT_DIR="/opt/nutanix-pxe"
rm -rf "$PROJECT_DIR"
git clone --branch "$GITHUB_BRANCH" "$GITHUB_REPO" "$PROJECT_DIR"
cd "$PROJECT_DIR"
umount /mnt
chmod +x setup.sh
bash setup.sh
bash scripts/reset-database.sh --clear-data --yes # Will reset the database

curl -X POST http://localhost:8080/api/config/nodes \
  -H "Content-Type: application/json" \
  -d '{
    "node_config": {
      "node_name": "nutanix-poc-bm-node-01",
      "server_profile": "cx3d-metal-48x128",
      "cluster_role": "compute-storage"
    },
    "network_config": {
      "workload_subnets": ['\"$WORKLOAD_SUBNET_ID\"']
    }
  }'

cat /var/log/nutanix-pxe/pxe-server.log
```

1. Monitor the install in the console


Tests:

curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/config?mgmt_ip=10.240.0.10"

## iPXE URL for bare metal server

`http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/config?mgmt_ip=10.240.0.10`
`http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/config?mgmt_ip=${net0/ip}`

to test the response:

`curl http://localhost:8080/boot/config?mgmt_ip=10.240.0.10`
`curl http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/config?mgmt_ip=10.240.0.10`

## config for server

curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/server/10.240.0.10"

# Create a cluster

To test build a single node cluster:

1. Ensure you have a node in the database with `deployment_status='deployed'` and proper `nutanix_config` values
2. Make a POST request to `/api/config/clusters` with the following payload:
   ```json
   {
     "cluster_config": {
       "cluster_type": "single_node",
       "cluster_name": "test-single-cluster",
       "nodes": ["your-node-name"]
     }
   }
   ```

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
     "cluster_config": {
       "cluster_type": "single_node",
       "cluster_name": "test-single-cluster",
       "nodes": ["nutanix-poc-bm-node-01"]
     }
   }' \
  "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/clusters"
```

3. Check the cluster creation status by making a GET request to `/api/config/clusters/{cluster_id}`

```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/clusters/{cluster_id}"
```

Where `{cluster_id}` is the ID returned in the creation response.


## To boot from the iso (livecd files not found)

```bash
#!ipxe
:retry_dhcp
dhcp || goto retry_dhcp
sleep 2
ntp time.adn.networklayer.com

# Set longer timeouts (values in milliseconds)
set net-timeout 300000
set http-timeout 300000

set base-url http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/images

# Boot with parameters to specify ISO location
sanboot --drive 0x80 ${base-url}/nutanix-ce.iso
```

```bash
#!ipxe
:retry_dhcp
dhcp || goto retry_dhcp
sleep 2
ntp time.adn.networklayer.com

# Set longer timeouts (values in milliseconds)
set net-timeout 300000
set http-timeout 300000

set base-url http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/images

# Boot with explicit ISO location
kernel ${base-url}/kernel iso-url=${base-url}/nutanix-ce.iso init=/ce_installer intel_iommu=on iommu=pt kvm-intel.nested=1 kvm.ignore_msrs=1 kvm-intel.ept=1 vga=791 net.ifnames=0 mpt3sas.prot_mask=1 IMG=squashfs LIVEFS_URL=${base-url}/nutanix-ce.iso
initrd ${base-url}/initrd-vpc.img
boot
```



## Boot

```bash
#!ipxe
:retry_dhcp
dhcp || goto retry_dhcp
sleep 2
ntp time.adn.networklayer.com
set base-url http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/images
set iso_url ${base-url}/nutanix-ce.iso

kernel http://your-server.com/memdisk iso raw
initrd ${iso_url} iso

boot || goto error

:error
echo Boot failed - dropping to shell
shell
```


## Log files

`deploy.sh` logs to `/var/log/nutanix-deployment.log`
`setup.sh` logs to `/var/log/nutanix-pxe-setup.log` tests are logged to `nutanix-pxe-tests.log`
`app.py`, `ibm_cloud_client.py` logs to `/var/log/nutanix-pxe/pxe-server.log`
`nginx` logs to `access.log` and `error.log`
`gunicorn` logs to `/var/log/nutanix-pxe/gunicorn-access.log` and `/var/log/nutanix-pxe/gunicorn-error.log`


## Manualy run the app

```bash
sudo systemctl stop nutanix-pxe
sudo -u nutanix ./venv/bin/python app.py
```

## Test gunicorn manually:
```bash
cd /opt/nutanix-pxe
source /etc/profile.d/app-vars.sh
sudo -u nutanix -E bash -c "source venv/bin/activate && gunicorn --bind 0.0.0.0:8080 --workers 1 app:app"
```

systemctl status nutanix-pxe

tail -n 50 /var/log/nutanix-pxe/gunicorn-error.log


`pip index versions ibm-vpc`

```bash
WARNING: pip index is currently an experimental command. It may be removed/changed in a future release without prior warning.
ibm-vpc (0.30.0)
Available versions: 0.30.0, 0.29.1, 0.29.0, 0.28.1, 0.28.0, 0.27.0, 0.26.3, 0.25.0, 0.24.1, 0.23.0, 0.22.0, 0.21.0, 0.20.0, 0.19.1, 0.19.0, 0.18.0, 0.17.0, 0.16.0, 0.15.0, 0.14.0, 0.13.0, 0.12.0, 0.11.1, 0.11.0, 0.10.0, 0.9.0, 0.8.0, 0.7.0, 0.6.0, 0.5.1, 0.4.1, 0.4.0, 0.3.0, 0.2.0, 0.1.0, 0.0.3, 0.0.2
  INSTALLED: 0.30.0
  LATEST:    0.30.0
```

`python3 -c "from ibm_vpc import VpcV1; help(VpcV1.create_bare_metal_server)"`

```bash
create_bare_metal_server(self, bare_metal_server_prototype: 'BareMetalServerPrototype', **kwargs) -> ibm_cloud_sdk_core.detailed_response.DetailedResponse
    Create a bare metal server.
    
    This request provisions a new bare metal server from a prototype object. The
    prototype object is structured in the same way as a retrieved bare metal server,
    and contains the information necessary to provision the new bare metal server. The
    bare metal server is automatically started.
    
    :param BareMetalServerPrototype bare_metal_server_prototype: The bare metal
           server prototype object.
    :param dict headers: A `dict` containing the request headers
    :return: A `DetailedResponse` containing the result, headers and HTTP status code.
    :rtype: DetailedResponse with `dict` result representing a `BareMetalServer` object
```

`python3 -c "from ibm_vpc import VpcV1; print(VpcV1.create_bare_metal_server.__doc__)"`

```bash

        Create a bare metal server.

        This request provisions a new bare metal server from a prototype object. The
        prototype object is structured in the same way as a retrieved bare metal server,
        and contains the information necessary to provision the new bare metal server. The
        bare metal server is automatically started.

        :param BareMetalServerPrototype bare_metal_server_prototype: The bare metal
               server prototype object.
        :param dict headers: A `dict` containing the request headers
        :return: A `DetailedResponse` containing the result, headers and HTTP status code.
        :rtype: DetailedResponse with `dict` result representing a `BareMetalServer` object
```

`python3 -c "from ibm_vpc import vpc_v1; print([attr for attr in dir(vpc_v1) if 'BareMetal' in attr])"`

```bash
['BareMetalServer', 'BareMetalServerBootTarget', 'BareMetalServerBootTargetBareMetalServerDiskReference', 'BareMetalServerCPU', 'BareMetalServerCollection', 'BareMetalServerConsoleAccessToken', 'BareMetalServerDisk', 'BareMetalServerDiskCollection', 'BareMetalServerDiskPatch', 'BareMetalServerFirmware', 'BareMetalServerHealthReason', 'BareMetalServerInitialization', 'BareMetalServerInitializationPrototype', 'BareMetalServerInitializationUserAccount', 'BareMetalServerInitializationUserAccountBareMetalServerInitializationHostUserAccount', 'BareMetalServerLifecycleReason', 'BareMetalServerNetworkAttachment', 'BareMetalServerNetworkAttachmentByPCI', 'BareMetalServerNetworkAttachmentByVLAN', 'BareMetalServerNetworkAttachmentCollection', 'BareMetalServerNetworkAttachmentPatch', 'BareMetalServerNetworkAttachmentPrototype', 'BareMetalServerNetworkAttachmentPrototypeBareMetalServerNetworkAttachmentByPCIPrototype', 'BareMetalServerNetworkAttachmentPrototypeBareMetalServerNetworkAttachmentByVLANPrototype', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterface', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentity', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfacePrototypeBareMetalServerNetworkAttachmentContext', 'BareMetalServerNetworkAttachmentReference', 'BareMetalServerNetworkAttachmentsPager', 'BareMetalServerNetworkInterface', 'BareMetalServerNetworkInterfaceByHiperSocket', 'BareMetalServerNetworkInterfaceByPCI', 'BareMetalServerNetworkInterfaceByVLAN', 'BareMetalServerNetworkInterfaceCollection', 'BareMetalServerNetworkInterfacePatch', 'BareMetalServerNetworkInterfacePrototype', 'BareMetalServerNetworkInterfacePrototypeBareMetalServerNetworkInterfaceByHiperSocketPrototype', 'BareMetalServerNetworkInterfacePrototypeBareMetalServerNetworkInterfaceByPCIPrototype', 'BareMetalServerNetworkInterfacePrototypeBareMetalServerNetworkInterfaceByVLANPrototype', 'BareMetalServerNetworkInterfacesPager', 'BareMetalServerPatch', 'BareMetalServerPrimaryNetworkAttachmentPrototype', 'BareMetalServerPrimaryNetworkAttachmentPrototypeBareMetalServerPrimaryNetworkAttachmentByPCIPrototype', 'BareMetalServerPrimaryNetworkInterfacePrototype', 'BareMetalServerProfile', 'BareMetalServerProfileBandwidth', 'BareMetalServerProfileBandwidthDependent', 'BareMetalServerProfileBandwidthEnum', 'BareMetalServerProfileBandwidthFixed', 'BareMetalServerProfileBandwidthRange', 'BareMetalServerProfileCPUArchitecture', 'BareMetalServerProfileCPUCoreCount', 'BareMetalServerProfileCPUCoreCountDependent', 'BareMetalServerProfileCPUCoreCountEnum', 'BareMetalServerProfileCPUCoreCountFixed', 'BareMetalServerProfileCPUCoreCountRange', 'BareMetalServerProfileCPUSocketCount', 'BareMetalServerProfileCPUSocketCountDependent', 'BareMetalServerProfileCPUSocketCountEnum', 'BareMetalServerProfileCPUSocketCountFixed', 'BareMetalServerProfileCPUSocketCountRange', 'BareMetalServerProfileCollection', 'BareMetalServerProfileConsoleTypes', 'BareMetalServerProfileDisk', 'BareMetalServerProfileDiskQuantity', 'BareMetalServerProfileDiskQuantityDependent', 'BareMetalServerProfileDiskQuantityEnum', 'BareMetalServerProfileDiskQuantityFixed', 'BareMetalServerProfileDiskQuantityRange', 'BareMetalServerProfileDiskSize', 'BareMetalServerProfileDiskSizeDependent', 'BareMetalServerProfileDiskSizeEnum', 'BareMetalServerProfileDiskSizeFixed', 'BareMetalServerProfileDiskSizeRange', 'BareMetalServerProfileDiskSupportedInterfaces', 'BareMetalServerProfileIdentity', 'BareMetalServerProfileIdentityByHref', 'BareMetalServerProfileIdentityByName', 'BareMetalServerProfileMemory', 'BareMetalServerProfileMemoryDependent', 'BareMetalServerProfileMemoryEnum', 'BareMetalServerProfileMemoryFixed', 'BareMetalServerProfileMemoryRange', 'BareMetalServerProfileNetworkAttachmentCount', 'BareMetalServerProfileNetworkAttachmentCountDependent', 'BareMetalServerProfileNetworkAttachmentCountRange', 'BareMetalServerProfileNetworkInterfaceCount', 'BareMetalServerProfileNetworkInterfaceCountDependent', 'BareMetalServerProfileNetworkInterfaceCountRange', 'BareMetalServerProfileOSArchitecture', 'BareMetalServerProfileReference', 'BareMetalServerProfileReservationTerms', 'BareMetalServerProfileSupportedTrustedPlatformModuleModes', 'BareMetalServerProfileVirtualNetworkInterfacesSupported', 'BareMetalServerProfilesPager', 'BareMetalServerPrototype', 'BareMetalServerPrototypeBareMetalServerByNetworkAttachment', 'BareMetalServerPrototypeBareMetalServerByNetworkInterface', 'BareMetalServerReservationAffinity', 'BareMetalServerReservationAffinityPatch', 'BareMetalServerReservationAffinityPrototype', 'BareMetalServerStatusReason', 'BareMetalServerTrustedPlatformModule', 'BareMetalServerTrustedPlatformModulePatch', 'BareMetalServerTrustedPlatformModulePrototype', 'BareMetalServersPager', 'FloatingIPTargetBareMetalServerNetworkInterfaceReference', 'FloatingIPTargetPatchBareMetalServerNetworkInterfaceIdentity', 'FloatingIPTargetPatchBareMetalServerNetworkInterfaceIdentityBareMetalServerNetworkInterfaceIdentityByHref', 'FloatingIPTargetPatchBareMetalServerNetworkInterfaceIdentityBareMetalServerNetworkInterfaceIdentityById', 'FloatingIPTargetPrototypeBareMetalServerNetworkInterfaceIdentity', 'FloatingIPTargetPrototypeBareMetalServerNetworkInterfaceIdentityBareMetalServerNetworkInterfaceIdentityByHref', 'FloatingIPTargetPrototypeBareMetalServerNetworkInterfaceIdentityBareMetalServerNetworkInterfaceIdentityById', 'NetworkInterfaceBareMetalServerContextReference', 'ReservationProfileBareMetalServerProfileReference', 'ReservedIPCollectionBareMetalServerNetworkInterfaceContext', 'ReservedIPTargetBareMetalServerNetworkInterfaceReferenceTargetContext', 'SecurityGroupTargetReferenceBareMetalServerNetworkInterfaceReferenceTargetContext', 'VirtualNetworkInterfaceTargetBareMetalServerNetworkAttachmentReferenceVirtualNetworkInterfaceContext']
```

`python3 -c "from ibm_vpc.vpc_v1 import BareMetalServerPrototype; print(BareMetalServerPrototype.__doc__)"`

```bash
BareMetalServerPrototype.

    :param int bandwidth: (optional) The total bandwidth (in megabits per second)
          shared across the bare metal server's network interfaces. The specified value
          must match one of the bandwidth values in the bare metal server's profile. If
          unspecified, the default value from the profile will be used.
    :param bool enable_secure_boot: (optional) Indicates whether secure boot is
          enabled. If enabled, the image must support secure boot or the server will fail
          to boot.
    :param BareMetalServerInitializationPrototype initialization:
    :param str name: (optional) The name for this bare metal server. The name must
          not be used by another bare metal server in the region. If unspecified, the name
          will be a hyphenated list of randomly-selected words.
          The system hostname will be based on this name.
    :param BareMetalServerProfileIdentity profile: The
          [profile](https://cloud.ibm.com/docs/vpc?topic=vpc-bare-metal-servers-profile)
          to use for this bare metal server.
    :param BareMetalServerReservationAffinityPrototype reservation_affinity:
          (optional)
    :param ResourceGroupIdentity resource_group: (optional) The resource group to
          use. If unspecified, the account's [default resource
          group](https://cloud.ibm.com/apidocs/resource-manager#introduction) will be
          used.
    :param BareMetalServerTrustedPlatformModulePrototype trusted_platform_module:
          (optional)
    :param VPCIdentity vpc: (optional) The VPC this bare metal server will reside
          in.
          If specified, it must match the VPC for the subnets that the network attachments
          or
          network interfaces of the bare metal server are attached to.
    :param ZoneIdentity zone: The zone this bare metal server will reside in.
```

`python3 -c "from ibm_vpc.vpc_v1 import BareMetalServerInitializationPrototype; print([attr for attr in dir(BareMetalServerInitializationPrototype) if not attr.startswith('_')])"`

```bash
['from_dict', 'to_dict']
```

`python3 -c "from ibm_vpc.vpc_v1 import BareMetalServerInitializationPrototype; print(BareMetalServerInitializationPrototype.__doc__)"`

```bash
    BareMetalServerInitializationPrototype.

    :param ImageIdentity image: The image to be used when provisioning the bare
          metal server.
    :param List[KeyIdentity] keys: The public SSH keys to install on the bare metal
          server. Keys will be made available to the bare metal server as cloud-init
          vendor data. For cloud-init enabled images, these keys will also be added as SSH
          authorized keys for the [default
          user](https://cloud.ibm.com/docs/vpc?topic=vpc-vsi_is_connecting_linux#determining-default-user-account).
          For Windows images, at least one key must be specified, and one will be selected
          to encrypt the administrator password. Keys are optional for other images, but
          if no keys are specified, the bare metal server will be inaccessible unless the
          specified image provides another means of access.
    :param str user_data: (optional) The user data to be made available when
          initializing the bare metal server.
```

`python3 -c "from ibm_vpc import vpc_v1; print([attr for attr in dir(vpc_v1) if 'ImageIdentity' in attr])"`

```bash
['ImageIdentity', 'ImageIdentityByCRN', 'ImageIdentityByHref', 'ImageIdentityById']
```

`python3 -c "from ibm_vpc.vpc_v1 import ImageIdentityById; print(ImageIdentityById.__doc__)"`

```bash
    ImageIdentityById.

    :param str id: The unique identifier for this image.
```

`python3 -c "from ibm_vpc import vpc_v1; print([attr for attr in dir(vpc_v1) if 'NetworkAttachment' in attr and 'Prototype' in attr])"`

```bash
['BareMetalServerNetworkAttachmentPrototype', 'BareMetalServerNetworkAttachmentPrototypeBareMetalServerNetworkAttachmentByPCIPrototype', 'BareMetalServerNetworkAttachmentPrototypeBareMetalServerNetworkAttachmentByVLANPrototype', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterface', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentity', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfacePrototypeBareMetalServerNetworkAttachmentContext', 'BareMetalServerPrimaryNetworkAttachmentPrototype', 'BareMetalServerPrimaryNetworkAttachmentPrototypeBareMetalServerPrimaryNetworkAttachmentByPCIPrototype', 'BareMetalServerPrototypeBareMetalServerByNetworkAttachment', 'FlowLogCollectorTargetPrototypeInstanceNetworkAttachmentIdentity', 'FlowLogCollectorTargetPrototypeInstanceNetworkAttachmentIdentityInstanceNetworkAttachmentIdentityByHref', 'FlowLogCollectorTargetPrototypeInstanceNetworkAttachmentIdentityInstanceNetworkAttachmentIdentityById', 'InstanceClusterNetworkAttachmentBeforePrototype', 'InstanceClusterNetworkAttachmentBeforePrototypeInstanceClusterNetworkAttachmentIdentityByHref', 'InstanceClusterNetworkAttachmentBeforePrototypeInstanceClusterNetworkAttachmentIdentityById', 'InstanceClusterNetworkAttachmentPrototypeClusterNetworkInterface', 'InstanceClusterNetworkAttachmentPrototypeClusterNetworkInterfaceClusterNetworkInterfaceIdentity', 'InstanceClusterNetworkAttachmentPrototypeClusterNetworkInterfaceClusterNetworkInterfaceIdentityClusterNetworkInterfaceIdentityByHref', 'InstanceClusterNetworkAttachmentPrototypeClusterNetworkInterfaceClusterNetworkInterfaceIdentityClusterNetworkInterfaceIdentityById', 'InstanceClusterNetworkAttachmentPrototypeClusterNetworkInterfaceInstanceClusterNetworkInterfacePrototypeInstanceClusterNetworkAttachment', 'InstanceClusterNetworkAttachmentPrototypeInstanceContext', 'InstanceNetworkAttachmentPrototype', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterface', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentity', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfacePrototypeInstanceNetworkAttachmentContext', 'InstancePrototypeInstanceByCatalogOfferingInstanceByCatalogOfferingInstanceByNetworkAttachment', 'InstancePrototypeInstanceByImageInstanceByImageInstanceByNetworkAttachment', 'InstancePrototypeInstanceBySourceSnapshotInstanceBySourceSnapshotInstanceByNetworkAttachment', 'InstancePrototypeInstanceByVolumeInstanceByVolumeInstanceByNetworkAttachment', 'InstanceTemplatePrototypeInstanceTemplateByCatalogOfferingInstanceTemplateByCatalogOfferingInstanceByNetworkAttachment', 'InstanceTemplatePrototypeInstanceTemplateByImageInstanceTemplateByImageInstanceByNetworkAttachment', 'InstanceTemplatePrototypeInstanceTemplateBySourceSnapshotInstanceTemplateBySourceSnapshotInstanceByNetworkAttachment']
```

`python3 -c "from ibm_vpc import vpc_v1; print([attr for attr in dir(vpc_v1) if 'Identity' in attr])"`

```bash
['AccountIdentity', 'AccountIdentityById', 'BackupPolicyScopePrototypeEnterpriseIdentity', 'BackupPolicyScopePrototypeEnterpriseIdentityEnterpriseIdentityByCRN', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentity', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'BareMetalServerProfileIdentity', 'BareMetalServerProfileIdentityByHref', 'BareMetalServerProfileIdentityByName', 'CatalogOfferingIdentity', 'CatalogOfferingIdentityCatalogOfferingByCRN', 'CatalogOfferingVersionIdentity', 'CatalogOfferingVersionIdentityCatalogOfferingVersionByCRN', 'CatalogOfferingVersionPlanIdentity', 'CatalogOfferingVersionPlanIdentityCatalogOfferingVersionPlanByCRN', 'CertificateInstanceIdentity', 'CertificateInstanceIdentityByCRN', 'CloudObjectStorageBucketIdentity', 'CloudObjectStorageBucketIdentityByCRN', 'CloudObjectStorageBucketIdentityCloudObjectStorageBucketIdentityByName', 'ClusterNetworkInterfacePrimaryIPPrototypeClusterNetworkSubnetReservedIPIdentityClusterNetworkInterfacePrimaryIPContext', 'ClusterNetworkInterfacePrimaryIPPrototypeClusterNetworkSubnetReservedIPIdentityClusterNetworkInterfacePrimaryIPContextByHref', 'ClusterNetworkInterfacePrimaryIPPrototypeClusterNetworkSubnetReservedIPIdentityClusterNetworkInterfacePrimaryIPContextById', 'ClusterNetworkProfileIdentity', 'ClusterNetworkProfileIdentityByHref', 'ClusterNetworkProfileIdentityByName', 'ClusterNetworkSubnetIdentity', 'ClusterNetworkSubnetIdentityByHref', 'ClusterNetworkSubnetIdentityById', 'DNSInstanceIdentity', 'DNSInstanceIdentityByCRN', 'DNSZoneIdentity', 'DNSZoneIdentityById', 'DedicatedHostGroupIdentity', 'DedicatedHostGroupIdentityByCRN', 'DedicatedHostGroupIdentityByHref', 'DedicatedHostGroupIdentityById', 'DedicatedHostProfileIdentity', 'DedicatedHostProfileIdentityByHref', 'DedicatedHostProfileIdentityByName', 'EncryptionKeyIdentity', 'EncryptionKeyIdentityByCRN', 'EndpointGatewayReservedIPReservedIPIdentity', 'EndpointGatewayReservedIPReservedIPIdentityByHref', 'EndpointGatewayReservedIPReservedIPIdentityById', 'FloatingIPTargetPatchBareMetalServerNetworkInterfaceIdentity', 'FloatingIPTargetPatchBareMetalServerNetworkInterfaceIdentityBareMetalServerNetworkInterfaceIdentityByHref', 'FloatingIPTargetPatchBareMetalServerNetworkInterfaceIdentityBareMetalServerNetworkInterfaceIdentityById', 'FloatingIPTargetPatchNetworkInterfaceIdentity', 'FloatingIPTargetPatchNetworkInterfaceIdentityNetworkInterfaceIdentityByHref', 'FloatingIPTargetPatchNetworkInterfaceIdentityNetworkInterfaceIdentityById', 'FloatingIPTargetPatchVirtualNetworkInterfaceIdentity', 'FloatingIPTargetPatchVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'FloatingIPTargetPatchVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'FloatingIPTargetPatchVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'FloatingIPTargetPrototypeBareMetalServerNetworkInterfaceIdentity', 'FloatingIPTargetPrototypeBareMetalServerNetworkInterfaceIdentityBareMetalServerNetworkInterfaceIdentityByHref', 'FloatingIPTargetPrototypeBareMetalServerNetworkInterfaceIdentityBareMetalServerNetworkInterfaceIdentityById', 'FloatingIPTargetPrototypeNetworkInterfaceIdentity', 'FloatingIPTargetPrototypeNetworkInterfaceIdentityNetworkInterfaceIdentityByHref', 'FloatingIPTargetPrototypeNetworkInterfaceIdentityNetworkInterfaceIdentityById', 'FloatingIPTargetPrototypeVirtualNetworkInterfaceIdentity', 'FloatingIPTargetPrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'FloatingIPTargetPrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'FloatingIPTargetPrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'FlowLogCollectorTargetPrototypeInstanceIdentity', 'FlowLogCollectorTargetPrototypeInstanceIdentityInstanceIdentityByCRN', 'FlowLogCollectorTargetPrototypeInstanceIdentityInstanceIdentityByHref', 'FlowLogCollectorTargetPrototypeInstanceIdentityInstanceIdentityById', 'FlowLogCollectorTargetPrototypeInstanceNetworkAttachmentIdentity', 'FlowLogCollectorTargetPrototypeInstanceNetworkAttachmentIdentityInstanceNetworkAttachmentIdentityByHref', 'FlowLogCollectorTargetPrototypeInstanceNetworkAttachmentIdentityInstanceNetworkAttachmentIdentityById', 'FlowLogCollectorTargetPrototypeNetworkInterfaceIdentity', 'FlowLogCollectorTargetPrototypeNetworkInterfaceIdentityNetworkInterfaceIdentityByHref', 'FlowLogCollectorTargetPrototypeNetworkInterfaceIdentityNetworkInterfaceIdentityById', 'FlowLogCollectorTargetPrototypeSubnetIdentity', 'FlowLogCollectorTargetPrototypeSubnetIdentitySubnetIdentityByCRN', 'FlowLogCollectorTargetPrototypeSubnetIdentitySubnetIdentityByHref', 'FlowLogCollectorTargetPrototypeSubnetIdentitySubnetIdentityById', 'FlowLogCollectorTargetPrototypeVPCIdentity', 'FlowLogCollectorTargetPrototypeVPCIdentityVPCIdentityByCRN', 'FlowLogCollectorTargetPrototypeVPCIdentityVPCIdentityByHref', 'FlowLogCollectorTargetPrototypeVPCIdentityVPCIdentityById', 'FlowLogCollectorTargetPrototypeVirtualNetworkInterfaceIdentity', 'FlowLogCollectorTargetPrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'FlowLogCollectorTargetPrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'FlowLogCollectorTargetPrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'ImageIdentity', 'ImageIdentityByCRN', 'ImageIdentityByHref', 'ImageIdentityById', 'InstanceClusterNetworkAttachmentBeforePrototypeInstanceClusterNetworkAttachmentIdentityByHref', 'InstanceClusterNetworkAttachmentBeforePrototypeInstanceClusterNetworkAttachmentIdentityById', 'InstanceClusterNetworkAttachmentPrototypeClusterNetworkInterfaceClusterNetworkInterfaceIdentity', 'InstanceClusterNetworkAttachmentPrototypeClusterNetworkInterfaceClusterNetworkInterfaceIdentityClusterNetworkInterfaceIdentityByHref', 'InstanceClusterNetworkAttachmentPrototypeClusterNetworkInterfaceClusterNetworkInterfaceIdentityClusterNetworkInterfaceIdentityById', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentity', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'InstanceNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'InstancePatchProfileInstanceProfileIdentityByHref', 'InstancePatchProfileInstanceProfileIdentityByName', 'InstancePlacementTargetPatchDedicatedHostGroupIdentity', 'InstancePlacementTargetPatchDedicatedHostGroupIdentityDedicatedHostGroupIdentityByCRN', 'InstancePlacementTargetPatchDedicatedHostGroupIdentityDedicatedHostGroupIdentityByHref', 'InstancePlacementTargetPatchDedicatedHostGroupIdentityDedicatedHostGroupIdentityById', 'InstancePlacementTargetPatchDedicatedHostIdentity', 'InstancePlacementTargetPatchDedicatedHostIdentityDedicatedHostIdentityByCRN', 'InstancePlacementTargetPatchDedicatedHostIdentityDedicatedHostIdentityByHref', 'InstancePlacementTargetPatchDedicatedHostIdentityDedicatedHostIdentityById', 'InstancePlacementTargetPrototypeDedicatedHostGroupIdentity', 'InstancePlacementTargetPrototypeDedicatedHostGroupIdentityDedicatedHostGroupIdentityByCRN', 'InstancePlacementTargetPrototypeDedicatedHostGroupIdentityDedicatedHostGroupIdentityByHref', 'InstancePlacementTargetPrototypeDedicatedHostGroupIdentityDedicatedHostGroupIdentityById', 'InstancePlacementTargetPrototypeDedicatedHostIdentity', 'InstancePlacementTargetPrototypeDedicatedHostIdentityDedicatedHostIdentityByCRN', 'InstancePlacementTargetPrototypeDedicatedHostIdentityDedicatedHostIdentityByHref', 'InstancePlacementTargetPrototypeDedicatedHostIdentityDedicatedHostIdentityById', 'InstancePlacementTargetPrototypePlacementGroupIdentity', 'InstancePlacementTargetPrototypePlacementGroupIdentityPlacementGroupIdentityByCRN', 'InstancePlacementTargetPrototypePlacementGroupIdentityPlacementGroupIdentityByHref', 'InstancePlacementTargetPrototypePlacementGroupIdentityPlacementGroupIdentityById', 'InstanceProfileIdentity', 'InstanceProfileIdentityByHref', 'InstanceProfileIdentityByName', 'InstanceTemplateIdentity', 'InstanceTemplateIdentityByCRN', 'InstanceTemplateIdentityByHref', 'InstanceTemplateIdentityById', 'KeyIdentity', 'KeyIdentityByCRN', 'KeyIdentityByFingerprint', 'KeyIdentityByHref', 'KeyIdentityById', 'LegacyCloudObjectStorageBucketIdentity', 'LegacyCloudObjectStorageBucketIdentityCloudObjectStorageBucketIdentityByName', 'LoadBalancerIdentity', 'LoadBalancerIdentityByCRN', 'LoadBalancerIdentityByHref', 'LoadBalancerIdentityById', 'LoadBalancerListenerDefaultPoolPatchLoadBalancerPoolIdentityByHref', 'LoadBalancerListenerDefaultPoolPatchLoadBalancerPoolIdentityById', 'LoadBalancerListenerIdentity', 'LoadBalancerListenerIdentityByHref', 'LoadBalancerListenerIdentityById', 'LoadBalancerListenerPolicyTargetPatchLoadBalancerListenerIdentity', 'LoadBalancerListenerPolicyTargetPatchLoadBalancerListenerIdentityLoadBalancerListenerIdentityByHref', 'LoadBalancerListenerPolicyTargetPatchLoadBalancerListenerIdentityLoadBalancerListenerIdentityById', 'LoadBalancerListenerPolicyTargetPatchLoadBalancerPoolIdentity', 'LoadBalancerListenerPolicyTargetPatchLoadBalancerPoolIdentityLoadBalancerPoolIdentityLoadBalancerPoolIdentityByHref', 'LoadBalancerListenerPolicyTargetPatchLoadBalancerPoolIdentityLoadBalancerPoolIdentityLoadBalancerPoolIdentityById', 'LoadBalancerListenerPolicyTargetPrototypeLoadBalancerListenerIdentity', 'LoadBalancerListenerPolicyTargetPrototypeLoadBalancerListenerIdentityLoadBalancerListenerIdentityByHref', 'LoadBalancerListenerPolicyTargetPrototypeLoadBalancerListenerIdentityLoadBalancerListenerIdentityById', 'LoadBalancerListenerPolicyTargetPrototypeLoadBalancerPoolIdentity', 'LoadBalancerListenerPolicyTargetPrototypeLoadBalancerPoolIdentityLoadBalancerPoolIdentityLoadBalancerPoolIdentityByHref', 'LoadBalancerListenerPolicyTargetPrototypeLoadBalancerPoolIdentityLoadBalancerPoolIdentityLoadBalancerPoolIdentityById', 'LoadBalancerPoolFailsafePolicyTargetPatchLoadBalancerPoolIdentityByHref', 'LoadBalancerPoolFailsafePolicyTargetPatchLoadBalancerPoolIdentityById', 'LoadBalancerPoolIdentity', 'LoadBalancerPoolIdentityByName', 'LoadBalancerPoolIdentityLoadBalancerPoolIdentityByHref', 'LoadBalancerPoolIdentityLoadBalancerPoolIdentityById', 'LoadBalancerPoolMemberTargetPrototypeInstanceIdentity', 'LoadBalancerPoolMemberTargetPrototypeInstanceIdentityInstanceIdentityByCRN', 'LoadBalancerPoolMemberTargetPrototypeInstanceIdentityInstanceIdentityByHref', 'LoadBalancerPoolMemberTargetPrototypeInstanceIdentityInstanceIdentityById', 'LoadBalancerPoolMemberTargetPrototypeLoadBalancerIdentity', 'LoadBalancerPoolMemberTargetPrototypeLoadBalancerIdentityLoadBalancerIdentityByCRN', 'LoadBalancerPoolMemberTargetPrototypeLoadBalancerIdentityLoadBalancerIdentityByHref', 'LoadBalancerPoolMemberTargetPrototypeLoadBalancerIdentityLoadBalancerIdentityById', 'LoadBalancerProfileIdentity', 'LoadBalancerProfileIdentityByHref', 'LoadBalancerProfileIdentityByName', 'NetworkACLIdentity', 'NetworkACLIdentityByCRN', 'NetworkACLIdentityByHref', 'NetworkACLIdentityById', 'NetworkACLRuleBeforePatchNetworkACLRuleIdentityByHref', 'NetworkACLRuleBeforePatchNetworkACLRuleIdentityById', 'NetworkACLRuleBeforePrototypeNetworkACLRuleIdentityByHref', 'NetworkACLRuleBeforePrototypeNetworkACLRuleIdentityById', 'NetworkInterfaceIPPrototypeReservedIPIdentity', 'NetworkInterfaceIPPrototypeReservedIPIdentityByHref', 'NetworkInterfaceIPPrototypeReservedIPIdentityById', 'OperatingSystemIdentity', 'OperatingSystemIdentityByHref', 'OperatingSystemIdentityByName', 'PublicGatewayFloatingIPPrototypeFloatingIPIdentity', 'PublicGatewayFloatingIPPrototypeFloatingIPIdentityFloatingIPIdentityByAddress', 'PublicGatewayFloatingIPPrototypeFloatingIPIdentityFloatingIPIdentityByCRN', 'PublicGatewayFloatingIPPrototypeFloatingIPIdentityFloatingIPIdentityByHref', 'PublicGatewayFloatingIPPrototypeFloatingIPIdentityFloatingIPIdentityById', 'PublicGatewayIdentity', 'PublicGatewayIdentityPublicGatewayIdentityByCRN', 'PublicGatewayIdentityPublicGatewayIdentityByHref', 'PublicGatewayIdentityPublicGatewayIdentityById', 'RegionIdentity', 'RegionIdentityByHref', 'RegionIdentityByName', 'ReservationIdentity', 'ReservationIdentityByCRN', 'ReservationIdentityByHref', 'ReservationIdentityById', 'ReservedIPTargetPrototypeEndpointGatewayIdentity', 'ReservedIPTargetPrototypeEndpointGatewayIdentityEndpointGatewayIdentityByCRN', 'ReservedIPTargetPrototypeEndpointGatewayIdentityEndpointGatewayIdentityByHref', 'ReservedIPTargetPrototypeEndpointGatewayIdentityEndpointGatewayIdentityById', 'ReservedIPTargetPrototypeVirtualNetworkInterfaceIdentity', 'ReservedIPTargetPrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'ReservedIPTargetPrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'ReservedIPTargetPrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'ResourceGroupIdentity', 'ResourceGroupIdentityById', 'RouteNextHopPatchVPNGatewayConnectionIdentity', 'RouteNextHopPatchVPNGatewayConnectionIdentityVPNGatewayConnectionIdentityByHref', 'RouteNextHopPatchVPNGatewayConnectionIdentityVPNGatewayConnectionIdentityById', 'RouteNextHopPrototypeVPNGatewayConnectionIdentity', 'RouteNextHopPrototypeVPNGatewayConnectionIdentityVPNGatewayConnectionIdentityByHref', 'RouteNextHopPrototypeVPNGatewayConnectionIdentityVPNGatewayConnectionIdentityById', 'RoutingTableIdentity', 'RoutingTableIdentityByCRN', 'RoutingTableIdentityByHref', 'RoutingTableIdentityById', 'SecurityGroupIdentity', 'SecurityGroupIdentityByCRN', 'SecurityGroupIdentityByHref', 'SecurityGroupIdentityById', 'SecurityGroupRuleRemotePatchSecurityGroupIdentity', 'SecurityGroupRuleRemotePatchSecurityGroupIdentitySecurityGroupIdentityByCRN', 'SecurityGroupRuleRemotePatchSecurityGroupIdentitySecurityGroupIdentityByHref', 'SecurityGroupRuleRemotePatchSecurityGroupIdentitySecurityGroupIdentityById', 'SecurityGroupRuleRemotePrototypeSecurityGroupIdentity', 'SecurityGroupRuleRemotePrototypeSecurityGroupIdentitySecurityGroupIdentityByCRN', 'SecurityGroupRuleRemotePrototypeSecurityGroupIdentitySecurityGroupIdentityByHref', 'SecurityGroupRuleRemotePrototypeSecurityGroupIdentitySecurityGroupIdentityById', 'ShareIdentity', 'ShareIdentityByCRN', 'ShareIdentityByHref', 'ShareIdentityById', 'ShareMountTargetVirtualNetworkInterfacePrototypeVirtualNetworkInterfaceIdentity', 'ShareMountTargetVirtualNetworkInterfacePrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByCRN', 'ShareMountTargetVirtualNetworkInterfacePrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityByHref', 'ShareMountTargetVirtualNetworkInterfacePrototypeVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById', 'ShareProfileIdentity', 'ShareProfileIdentityByHref', 'ShareProfileIdentityByName', 'ShareSourceSnapshotPrototypeShareSnapshotIdentity', 'ShareSourceSnapshotPrototypeShareSnapshotIdentityShareSnapshotIdentityByCRN', 'ShareSourceSnapshotPrototypeShareSnapshotIdentityShareSnapshotIdentityByHref', 'ShareSourceSnapshotPrototypeShareSnapshotIdentityShareSnapshotIdentityById', 'SnapshotIdentity', 'SnapshotIdentityByCRN', 'SnapshotIdentityByHref', 'SnapshotIdentityById', 'SubnetIdentity', 'SubnetIdentityByCRN', 'SubnetIdentityByHref', 'SubnetIdentityById', 'SubnetPublicGatewayPatchPublicGatewayIdentityByCRN', 'SubnetPublicGatewayPatchPublicGatewayIdentityByHref', 'SubnetPublicGatewayPatchPublicGatewayIdentityById', 'TrustedProfileIdentity', 'TrustedProfileIdentityByCRN', 'TrustedProfileIdentityById', 'VPCDNSResolverVPCPatchVPCIdentityByCRN', 'VPCDNSResolverVPCPatchVPCIdentityByHref', 'VPCDNSResolverVPCPatchVPCIdentityById', 'VPCIdentity', 'VPCIdentityByCRN', 'VPCIdentityByHref', 'VPCIdentityById', 'VPNGatewayConnectionIKEIdentity', 'VPNGatewayConnectionIKEIdentityPrototype', 'VPNGatewayConnectionIKEIdentityPrototypeVPNGatewayConnectionIKEIdentityFQDN', 'VPNGatewayConnectionIKEIdentityPrototypeVPNGatewayConnectionIKEIdentityHostname', 'VPNGatewayConnectionIKEIdentityPrototypeVPNGatewayConnectionIKEIdentityIPv4', 'VPNGatewayConnectionIKEIdentityPrototypeVPNGatewayConnectionIKEIdentityKeyID', 'VPNGatewayConnectionIKEIdentityVPNGatewayConnectionIKEIdentityFQDN', 'VPNGatewayConnectionIKEIdentityVPNGatewayConnectionIKEIdentityHostname', 'VPNGatewayConnectionIKEIdentityVPNGatewayConnectionIKEIdentityIPv4', 'VPNGatewayConnectionIKEIdentityVPNGatewayConnectionIKEIdentityKeyID', 'VPNGatewayConnectionIKEPolicyPatchIKEPolicyIdentityByHref', 'VPNGatewayConnectionIKEPolicyPatchIKEPolicyIdentityById', 'VPNGatewayConnectionIKEPolicyPrototypeIKEPolicyIdentityByHref', 'VPNGatewayConnectionIKEPolicyPrototypeIKEPolicyIdentityById', 'VPNGatewayConnectionIPsecPolicyPatchIPsecPolicyIdentityByHref', 'VPNGatewayConnectionIPsecPolicyPatchIPsecPolicyIdentityById', 'VPNGatewayConnectionIPsecPolicyPrototypeIPsecPolicyIdentityByHref', 'VPNGatewayConnectionIPsecPolicyPrototypeIPsecPolicyIdentityById', 'VirtualNetworkInterfaceIPPrototypeReservedIPIdentityVirtualNetworkInterfaceIPsContext', 'VirtualNetworkInterfaceIPPrototypeReservedIPIdentityVirtualNetworkInterfaceIPsContextByHref', 'VirtualNetworkInterfaceIPPrototypeReservedIPIdentityVirtualNetworkInterfaceIPsContextById', 'VirtualNetworkInterfacePrimaryIPPrototypeReservedIPIdentityVirtualNetworkInterfacePrimaryIPContext', 'VirtualNetworkInterfacePrimaryIPPrototypeReservedIPIdentityVirtualNetworkInterfacePrimaryIPContextByHref', 'VirtualNetworkInterfacePrimaryIPPrototypeReservedIPIdentityVirtualNetworkInterfacePrimaryIPContextById', 'VolumeAttachmentPrototypeVolumeVolumeIdentity', 'VolumeAttachmentPrototypeVolumeVolumeIdentityVolumeIdentityByCRN', 'VolumeAttachmentPrototypeVolumeVolumeIdentityVolumeIdentityByHref', 'VolumeAttachmentPrototypeVolumeVolumeIdentityVolumeIdentityById', 'VolumeIdentity', 'VolumeIdentityByCRN', 'VolumeIdentityByHref', 'VolumeIdentityById', 'VolumeProfileIdentity', 'VolumeProfileIdentityByHref', 'VolumeProfileIdentityByName', 'ZoneIdentity', 'ZoneIdentityByHref', 'ZoneIdentityByName']
```

`python3 -c "from ibm_vpc.vpc_v1 import BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterface; print(BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterface.__doc__)"`

This iPXE script:

Uses the #!ipxe shebang to indicate it's an iPXE script
Issues a dhcp command to configure the network interface
Uses the chain command to load another iPXE script from our PXE server at the endpoint /boot/node/{node_id}


#!ipxe
:retry_dhcp
dhcp || goto retry_dhcp
sleep 2
ntp time.adn.networklayer.com
initrd --name initrd http://pxe-server/initrd.img
kernel http://pxe-server/vmlinuz console=tty0 console=ttyS0,115200
boot


```bash
2025-08-04 15:11:52,238 - app - INFO - 127.0.0.1 - API Request received: POST http://localhost:8080/api/config/nodes
2025-08-04 15:11:52,239 - app - INFO - 127.0.0.1 - Request headers: {'Host': 'localhost:8080', 'User-Agent': 'curl/7.81.0', 'Accept': '*/*', 'Content-Type': 'application/json', 'Content-Length': '265'}
2025-08-04 15:11:52,239 - app - INFO - 127.0.0.1 - Request data: {'node_config': {'node_name': 'nutanix-poc-bm-node-01', 'server_profile': 'cx3d-metal-48x128', 'cluster_role': 'compute-storage'}, 'network_config': {'workload_subnets': ['0717-c0873ef3-c17d-4b51-a1db-b03c2309c65c']}}
2025-08-04 15:11:52,239 - app - INFO - 127.0.0.1 - Processed node configuration: {'node_name': 'nutanix-poc-bm-node-01', 'server_profile': 'cx3d-metal-48x128', 'cluster_role': 'compute-storage', 'network_config': {'workload_subnets': ['0717-c0873ef3-c17d-4b51-a1db-b03c2309c65c']}}
2025-08-04 15:11:52,239 - node_provisioner - INFO - 127.0.0.1 - Starting provisioning for node nutanix-poc-bm-node-01
2025-08-04 15:11:52,250 - node_provisioner - INFO - 127.0.0.1 - Checking for existing node with name nutanix-poc-bm-node-01: None
2025-08-04 15:11:52,250 - node_provisioner - INFO - 127.0.0.1 - Reserving IPs for node nutanix-poc-bm-node-01
2025-08-04 15:11:55,523 - ibm_cloud_client - INFO - 127.0.0.1 - Reserved IP 10.240.0.10 in subnet 0717-10e2ee7f-fd10-41b0-8324-730fbe78913a
2025-08-04 15:11:56,534 - ibm_cloud_client - INFO - 127.0.0.1 - Reserved IP 10.240.0.51 in subnet 0717-10e2ee7f-fd10-41b0-8324-730fbe78913a
2025-08-04 15:11:56,761 - ibm_cloud_client - INFO - 127.0.0.1 - Reserved IP 10.240.0.101 in subnet 0717-10e2ee7f-fd10-41b0-8324-730fbe78913a
2025-08-04 15:11:56,900 - ibm_cloud_client - INFO - 127.0.0.1 - Reserved IP 10.240.1.10 in subnet 0717-c0873ef3-c17d-4b51-a1db-b03c2309c65c
2025-08-04 15:11:57,792 - ibm_cloud_client - INFO - 127.0.0.1 - Reserved IP 10.240.0.200 in subnet 0717-10e2ee7f-fd10-41b0-8324-730fbe78913a
2025-08-04 15:11:57,805 - database - INFO - 127.0.0.1 - IP reservations stored for nutanix-poc-bm-node-01
2025-08-04 15:11:57,805 - node_provisioner - INFO - 127.0.0.1 - IP reservation completed for nutanix-poc-bm-node-01
2025-08-04 15:11:57,806 - node_provisioner - INFO - 127.0.0.1 - Registering DNS records for nutanix-poc-bm-node-01
2025-08-04 15:11:57,806 - ibm_cloud_client - INFO - 127.0.0.1 - Attempting to create DNS record: nutanix-poc-bm-node-01-mgmt (A) -> 10.240.0.10
2025-08-04 15:11:57,806 - ibm_cloud_client - INFO - 127.0.0.1 - API call parameters: instance_id=64c20679-d89a-45c0-94dc-71a0983c9218, dnszone_id=12e45047-a91c-4dd9-8de4-9d6297e63fc4, name=nutanix-poc-bm-node-01-mgmt, type=A, rdata={'ip': 10.240.0.10}, ttl=300
2025-08-04 15:11:59,990 - ibm_cloud_client - INFO - 127.0.0.1 - Created DNS record nutanix-poc-bm-node-01-mgmt -> 10.240.0.10
2025-08-04 15:11:59,990 - ibm_cloud_client - INFO - 127.0.0.1 - Attempting to create DNS record: nutanix-poc-bm-node-01-ahv (A) -> 10.240.0.51
2025-08-04 15:11:59,990 - ibm_cloud_client - INFO - 127.0.0.1 - API call parameters: instance_id=64c20679-d89a-45c0-94dc-71a0983c9218, dnszone_id=12e45047-a91c-4dd9-8de4-9d6297e63fc4, name=nutanix-poc-bm-node-01-ahv, type=A, rdata={'ip': 10.240.0.51}, ttl=300
2025-08-04 15:12:00,220 - ibm_cloud_client - INFO - 127.0.0.1 - Created DNS record nutanix-poc-bm-node-01-ahv -> 10.240.0.51
2025-08-04 15:12:00,220 - ibm_cloud_client - INFO - 127.0.0.1 - Attempting to create DNS record: nutanix-poc-bm-node-01-cvm (A) -> 10.240.0.101
2025-08-04 15:12:00,220 - ibm_cloud_client - INFO - 127.0.0.1 - API call parameters: instance_id=64c20679-d89a-45c0-94dc-71a0983c9218, dnszone_id=12e45047-a91c-4dd9-8de4-9d6297e63fc4, name=nutanix-poc-bm-node-01-cvm, type=A, rdata={'ip': 10.240.0.101}, ttl=300
2025-08-04 15:12:00,432 - ibm_cloud_client - INFO - 127.0.0.1 - Created DNS record nutanix-poc-bm-node-01-cvm -> 10.240.0.101
2025-08-04 15:12:00,432 - ibm_cloud_client - INFO - 127.0.0.1 - Attempting to create DNS record: nutanix-poc-bm-node-01-workload (A) -> 10.240.1.10
2025-08-04 15:12:00,432 - ibm_cloud_client - INFO - 127.0.0.1 - API call parameters: instance_id=64c20679-d89a-45c0-94dc-71a0983c9218, dnszone_id=12e45047-a91c-4dd9-8de4-9d6297e63fc4, name=nutanix-poc-bm-node-01-workload, type=A, rdata={'ip': 10.240.1.10}, ttl=300
2025-08-04 15:12:00,648 - ibm_cloud_client - INFO - 127.0.0.1 - Created DNS record nutanix-poc-bm-node-01-workload -> 10.240.1.10
2025-08-04 15:12:00,649 - ibm_cloud_client - INFO - 127.0.0.1 - Attempting to create DNS record: cluster01 (A) -> 10.240.0.200
2025-08-04 15:12:00,649 - ibm_cloud_client - INFO - 127.0.0.1 - API call parameters: instance_id=64c20679-d89a-45c0-94dc-71a0983c9218, dnszone_id=12e45047-a91c-4dd9-8de4-9d6297e63fc4, name=cluster01, type=A, rdata={'ip': 10.240.0.200}, ttl=300
2025-08-04 15:12:00,850 - ibm_cloud_client - INFO - 127.0.0.1 - Created DNS record cluster01 -> 10.240.0.200
2025-08-04 15:12:00,862 - database - INFO - 127.0.0.1 - DNS records stored for nutanix-poc-bm-node-01
2025-08-04 15:12:00,862 - node_provisioner - INFO - 127.0.0.1 - DNS registration completed for nutanix-poc-bm-node-01
2025-08-04 15:12:00,862 - node_provisioner - INFO - 127.0.0.1 - Creating VNIs for nutanix-poc-bm-node-01
2025-08-04 15:12:00,863 - ibm_cloud_client - INFO - 127.0.0.1 - Checking if create_virtual_network_interface method exists: True
2025-08-04 15:12:02,648 - ibm_cloud_client - INFO - 127.0.0.1 - Created virtual network interface nutanix-poc-bm-node-01-mgmt-vni
2025-08-04 15:12:02,649 - ibm_cloud_client - INFO - 127.0.0.1 - Checking if create_virtual_network_interface method exists: True
2025-08-04 15:12:04,397 - ibm_cloud_client - INFO - 127.0.0.1 - Created virtual network interface nutanix-poc-bm-node-01-workload-vni-1
2025-08-04 15:12:04,410 - database - INFO - 127.0.0.1 - vNIC info stored for nutanix-poc-bm-node-01
2025-08-04 15:12:04,410 - node_provisioner - INFO - 127.0.0.1 - VNI creation completed for nutanix-poc-bm-node-01
2025-08-04 15:12:04,410 - node_provisioner - INFO - 127.0.0.1 - Updating database for nutanix-poc-bm-node-01
2025-08-04 15:12:04,422 - database - INFO - 127.0.0.1 - Node nutanix-poc-bm-node-01 inserted with ID 1
2025-08-04 15:12:04,434 - node_provisioner - INFO - 127.0.0.1 - Database update completed for node ID 1
2025-08-04 15:12:04,434 - node_provisioner - INFO - 127.0.0.1 - Deploying bare metal server for node ID 1
2025-08-04 15:12:04,657 - ibm_cloud_client - INFO - 127.0.0.1 - User data being sent: http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/config?node_id=1
2025-08-04 15:12:04,658 - ibm_cloud_client - INFO - 127.0.0.1 - Bare metal server prototype: {'initialization': {'image': {'id': 'r006-bfef819d-11af-4252-9bd3-bae1d9dd8e1d'}, 'keys': [{'id': 'r006-20dafd86-68eb-4f94-a9a5-0d860a88ee43'}], 'user_data': 'http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/config?node_id=1'}, 'name': 'nutanix-poc-bm-node-01', 'profile': {'name': 'cx3d-metal-48x128'}, 'vpc': {'id': 'r006-3e58f38f-629a-492b-85f8-9e6bf9ec2747'}, 'zone': {'name': 'us-south-1'}, 'primary_network_attachment': {'name': 'nutanix-poc-bm-node-01-primary-attachment', 'virtual_network_interface': {'id': '0717-a09c3245-72d2-4d1d-983d-01e007c78c6f'}}}
2025-08-04 15:12:07,135 - ibm_cloud_client - INFO - 127.0.0.1 - Created bare metal server nutanix-poc-bm-node-01
2025-08-04 15:12:07,147 - database - INFO - 127.0.0.1 - Node 1 deployment info updated
2025-08-04 15:12:07,159 - node_provisioner - INFO - 127.0.0.1 - Bare metal deployment initiated for node 1
2025-08-04 15:12:07,171 - node_provisioner - INFO - 127.0.0.1 - Monitoring started for node 1
2025-08-04 15:12:07,171 - app - INFO - 127.0.0.1 - API Response (202): {'message': 'Node provisioning initiated successfully', 'node_id': 1, 'deployment_id': '0717-bb4ceb63-5b5f-475d-88e3-2dc3007245c1', 'estimated_completion': '2025-08-04T16:19:07.171841', 'monitoring_endpoint': '/api/status/nodes/1'}
2025-08-04 15:36:02,675 - boot_service - INFO - 10.240.0.10 - iPXE boot request from None (MAC: None)
2025-08-04 15:36:02,685 - boot_service - WARNING - 10.240.0.10 - Server None not found in configuration database
```

`python3 scripts/list_nodes.py --details 1`

```bash
Node Details for ID 1:
========================================
id: 1
node_name: nutanix-poc-bm-node-01
node_position: None
server_profile: cx3d-metal-48x128
cluster_role: compute-storage
  cluster_type: multi_node
deployment_status: deploying
bare_metal_id: 0717-bb4ceb63-5b5f-475d-88e3-2dc3007245c1
management_vnic_id: 0717-a09c3245-72d2-4d1d-983d-01e007c78c6f
management_ip: 10.240.0.10
workload_vnic_id: 0717-92f915e8-cb24-4a4f-86e7-49850df3c3ad
workload_ip: 10.240.1.10
nutanix_config:
  ahv_ip: 10.240.0.51
  cvm_ip: 10.240.0.101
  ahv_dns: nutanix-poc-bm-node-01-ahv.nutanix-ce-poc.cloud
  cvm_dns: nutanix-poc-bm-node-01-cvm.nutanix-ce-poc.cloud
  cluster_ip: 10.240.0.200
  cluster_dns: cluster01.nutanix-ce-poc.cloud
  cluster_type: multi_node
  storage_config: {}
progress_percentage: 0
current_phase: None
cluster_name: None
created_at: 2025-08-04 15:12:04.420621
updated_at: 2025-08-04 15:12:07.145722
workload_vnics: {'workload_vni_1': {'ip': '10.240.1.10', 'vnic_id': '0717-92f915e8-cb24-4a4f-86e7-49850df3c3ad', 'dns_name': 'nutanix-poc-bm-node-01-workload-1.nutanix-ce-poc.cloud', 'subnet_id': ''}}
```


You can reach the CVM based Foundation by going to http://yourCVM-IPaddress:8000

AOS is the operating system of the Nutanix Controller VM, which is a VM that must be running in the hypervisor to provide Nutanix-specific functionality.

Foundation is the official deployment software of Nutanix. Foundation allows you to configure a pre-imaged node, or image a node with a hypervisor and an AOS of your choice. Foundation also allows you to form a cluster out of nodes whose hypervisor and AOS versions are the same, with or without re-imaging. Foundation is available for download at https://portal.nutanix.com/#/page/Foundation.

If you already have a running cluster and want to add nodes to it, you must use the Expand Cluster option in Prism, instead of using Foundation. Expand Cluster allows you to directly re-image a node whose hypervisor/AOS version does not match the cluster's version.

Nutanix and its OEM partners install some software on a node at the factory, before shipping it to the customer. For shipments inside the USA, this software is a hypervisor and an AOS. For Nutanix factory nodes, the hypervisor is AHV. In case of the OEM factories, it is up to the vendor to decide what hypervisor to ship to the customer. However, they always install AOS, regardless of the hypervisor.

For shipments outside the USA, Nutanix installs a light-weight software called DiscoveryOS, which allows the node to be discovered in Foundation or in the Expand Cluster option of Prism.

Since a node with DiscoveryOS is not pre-imaged with a hypervisor and an AOS, it must go through imaging first before joining a cluster. Both Foundation and Expand Cluster allow you to directly image it with the correct hypervisor and AOS.

Vendors who do not have an OEM agreement with Nutanix ship a node without any software (not even DiscoveryOS) installed on it. Foundation supports bare-metal imaging of such nodes. In contrast, Expand Cluster does not support direct bare-metal imaging. Therefore, if you want to add a software-less node to an existing cluster, you must first image it using Foundation, then use Expand Cluster.

Foundation is a Nutanix provided tool used for bootstrapping, imaging, and deployment of Nutanix clusters. The imaging process will install the desired version of the AOS software and the hypervisor of your choice. One of the ways to use Foundation services is to make use of the APIs provided by Foundation https://www.nutanix.dev/api_reference/apis/foundation.html#section/Foundation.


https://portal.nutanix.com/page/documents/details?targetId=Nutanix-Community-Edition-Getting-Started-v2_1:Nutanix-Community-Edition-Getting-Started-v2_1

Installer ISO
https://download.nutanix.com/ce/2024.08.19/phoenix.x86_64-fnd_5.6.1_patch-aos_6.8.1_ga.iso

Nutanix VirtIO for Windows (x64 installer)(Version: 1.2.3)
https://download.nutanix.com/virtIO/1.2.3/Nutanix-VirtIO-1.2.3-x64.msi

Nutanix VirtIO for Windows (x86 installer) (Version: 1.2.3)
https://download.nutanix.com/virtIO/1.2.3/Nutanix-VirtIO-1.2.3-x86.msi


Nutanix VirtIO for Windows (iso) (Version: 1.2.3)
https://download.nutanix.com/virtIO/1.2.3/Nutanix-VirtIO-1.2.3.iso

After the host restarts, the AHV host and the CVM run their first boot setup processes. These processes can take 15 to 20 minutes to complete. After these processes finish running, you can perform the following steps:

Sign in to the CE host and open a secure shell session (SSH) to the CVM IP address.
Configure a single-node or multinode cluster.
See the Next Steps section.
For a multinode cluster, you must install CE on every node that you plan to use in the cluster. When the system restarts after installation, validate that the CVMs are online and ready to join a cluster.

## Step 5: Verify files are accessible

```bash
curl -I http://your-server-ip/squashfs.img
curl -I http://your-server-ip/arizona.cfg
```

### 5.1 Required File Structure
```bash
/var/www/pxe/images
├── kernel
├── initrd-vpc
├── squashfs.img
├── nutanix_installer_package.tar.gz
├── AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso
```

## Server Reinitialization Issues

When reinitializing a bare metal server, you might encounter issues with server state transitions. The reinitialization process involves:

1. Stopping the server
2. Waiting for the server to reach the "stopped" state
3. Updating the server initialization with iPXE boot configuration
4. Starting the server with the new configuration

### Common Issues

#### "Server not in the STOPPED status" Error

After updating the server initialization, the server state may change from "stopped" to "reinitializing" before you attempt to start it. This can cause a 409 error with the message "Failed to start the bare metal server because the server is not in the STOPPED status."

**Solution:**
- The system now automatically detects when a server is in "reinitializing" state and considers this a valid state for the reinitialization process.
- If you encounter this error, wait a few seconds and try again. The second attempt usually succeeds because the server has completed its state transition.
- The web interface has been updated to automatically handle this case and provide appropriate feedback.

#### Server State Detection Improvements

The system has been enhanced to better detect server state changes:

- **Adaptive Polling**: The system now polls more frequently initially (every 5 seconds for the first minute, then every 15 seconds for the next 4 minutes, then every 30 seconds) to catch state transitions more quickly.
- **Force Proceed Option**: After 5 minutes of waiting, the system will proceed even if the target state hasn't been reached, assuming that the IBM Cloud API might be reporting a different state than the actual server state.
- **Transitional State Handling**: The system now better handles transitional states like "stopping" and "reinitializing", and will proceed if the server has been in a transitional state for an extended period.
- **Detailed Logging**: More detailed logs are now generated, including elapsed time and consecutive state readings, to help diagnose issues.
- **Robust Polling Loop**: The polling loop has been made more robust with heartbeat logging, sleep checks, and comprehensive error handling to ensure it doesn't stop prematurely.
- **Segmented Sleep**: Instead of sleeping for the full interval at once, the system now sleeps in 1-second increments with periodic checks to ensure the polling process doesn't get stuck.

#### Interpreting Polling Logs

The polling logs now include prefixes to help identify different stages of the polling process:

- `POLL_START`: Indicates the start of the polling process
- `POLL_LOOP_START`: Indicates the start of the polling loop
- `POLL_ITERATION`: Indicates the start of a new polling iteration with count
- `POLL_CHECKING`: Indicates the system is checking the server state
- `POLL_STATE`: Shows the current server state
- `POLL_WAITING`: Indicates the system is waiting before the next check
- `POLL_SLEEP_CHECK`: Periodic check during sleep to ensure the process is still running
- `POLL_HEARTBEAT`: Periodic heartbeat message to confirm the polling is still active
- `POLL_ERROR`: Indicates an error occurred during polling
- `POLL_TIMEOUT`: Indicates the polling timed out
- `POLL_FINAL_CHECK`: Indicates the final state check before giving up
- `POLL_PARTIAL_SUCCESS`: Indicates the server is in a transitional state moving toward the target
- `POLL_END`: Indicates the end of the polling process

If you see polling stop unexpectedly, look for `POLL_ERROR` or `POLL_CRITICAL` messages in the logs, which indicate errors that might have caused the polling to stop.

#### "Failed to start server after multiple attempts" Error

If the server remains in "reinitializing" state for an extended period, the system may fail after multiple retry attempts.

**Solution:**
- Check the server status in the IBM Cloud console to verify its current state
- If the server is already starting or running, the reinitialization may have actually succeeded despite the error
- If the server is still in "reinitializing" state, wait a few minutes and try again

### Debugging Reinitialization

To debug server reinitialization issues:

1. Check the logs at `/var/log/nutanix-pxe/pxe-server.log` for detailed error messages
2. Verify the server state using the IBM Cloud CLI:
   ```bash
   ibmcloud is bare-metal-server <server_id>
   ```
3. If the server is stuck in a transitional state, you may need to contact IBM Cloud support

## Architecture

This solution works because the PXE/Config server is pre-configured with extracted and modified files from the Nutanix CE ISO file:

1. **iPXE** downloads **kernel** and **initrd** over HTTP.
2. **initrd** boots and downloads **squashfs.img** (root filesystem).
3. **Phoenix** installer reads **Arizona** config for automation.
4. Installs **AHV** hypervisor and **CVM** on bare metal.

This results in a node that is ready to be become a single node cluster, or join with other nodes in a standard cluster and be accessible via **Prism**.

```
IBM Bare Metal Server (iPXE) → HTTP Server → Automated Installation
                ↓
1. Boot kernel + initrd via HTTP
2. Download squashfs.img (root filesystem)  
3. Download arizona.cfg (automation config)
4. Download AOS installer + AHV ISO
5. Automated installation based on config
```