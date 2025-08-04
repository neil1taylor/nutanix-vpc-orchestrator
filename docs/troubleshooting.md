# Troublshooting

## Run the setup script

`setup.sh` is run during the cloud-int stage via `deploy.sh` but can be run again and the output seen on the console as well as `/var/log/nutanix-pxe-setup.log`. When run subsequent times, some things, like the database user, will fail as they have already been configured.

1. SSH to the pxe server

```bash
rm -rf /var/log/nutanix-pxe
cd /
GITHUB_REPO="https://github.com/neil1taylor/nutanix-vpc-orchestrator"
GITHUB_BRANCH="main"
PROJECT_DIR="/opt/nutanix-pxe"
rm -rf "$PROJECT_DIR"
git clone --branch "$GITHUB_BRANCH" "$GITHUB_REPO" "$PROJECT_DIR"
cd "$PROJECT_DIR"
chmod +x setup.sh
bash setup.sh
bash scripts/reset-database.sh --clear-data --yes
```

2. Monitor the install in the console


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