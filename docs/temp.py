# Copyright (c) 2017 Nutanix Inc. All rights reserved.
#
# Author: piyush.mittal@nutanix.com
#
#  ParamList object for storing imaging parameters.
#
# Default values will be used during PXE installs
# if the information is not provided in /proc/cmdline
# via the APPEND line of the pxecfg file

import json
import os
import re

import features
import net_info
import sysUtil
from consts import PHOENIX_VERSION, NTP_SERVERS, ValidationError
from log import ERROR
import six


class ParamList(object):

  def __init__(self):
    self.hyp_type                      = ""
    self.hyp_version                   = None
    self.hyp_distro                    = None
    self.hypervisor_iso_url            = None    # Location of hypervisor iso.
    self.hypervisor_iso_path           = None
    self.iso_whitelist_path            = None
    self.svmboot_iso_path              = None    # Used when imaging only hyp.
    self.model                         = None    # For code use.
    self.model_string                  = None    # For human eyes.
    self.node_position                 = None
    self.node_name                     = None
    self.svm_version                   = None
    self.nos_version                   = None    # Mirrors svm_version.
    self.block_id                      = None
    self.cluster_name                  = "NTNX"  # Used for internal imaging
    self.node_serial                   = None
    self.node_uuid                     = None
    self.cluster_id                    = None
    self.hyp_install_type              = "clean" # default value 'clean'
    self.svm_install_type              = "clean" # default value 'clean'
    self.delete_fb_on_success          = True    # Delete firstboot scripts
    self.monitoring_url_root           = None
    self.monitoring_url_retry_count    = None
    self.monitoring_url_timeout_secs   = None
    self.fc_imaged_node_uuid           = None
    self.fc_deployment_uuid            = None
    self.fc_phx_wf                     = False
    self.fc_settings                   = None
    self.vswitches                     = []
    self.host_interfaces               = []
    self.cvm_interfaces                = []
    self.host_ip                       = None    # Deprecated, use host_interfaces
    self.host_subnet_mask              = None    # Deprecated, use host_interfaces
    self.svm_ip                        = None    # Deprecated, use cvm_interfaces
    self.svm_subnet_mask               = None    # Deprecated, use cvm_interfaces
    self.svm_default_gw                = None    # Deprecated, use cvm_interfaces
    self.svm_gb_ram                    = None    # Used by PXE
    self.user_passed_svm_gb_ram        = True    # Used to decide SPDK mem assignment for RDM users
    self.svm_numa_nodes                = []
    self.svm_num_vcpus                 = None    # Used by PXE
    self.is_svm_vcpus_static_placement = True
    self.default_gw                    = None    # Deprecated, use host_interfaces
    self.dns_ip                        = None    # Used by PXE
    self.crypt_password                = None    # Encrypted password to inject
    self.boot_disk                     = None
    self.boot_disk_sz_sectors          = None
    self.boot_disk_sz_GB               = None
    self.volume_boot_drives            = []      # List of NVMe drives used by VROC RAID1
    self.volume_sz_GB                  = None    # RAID1 volume size
    self.volume_disks_sn               = {}      # Dict of RAID1 NVMe drives with Serial Number
    self.volume_name                   = None    # RAID1 Volume Name
    self.ptable_end_sector             = None
    self.partition_table_type          = None
    self.storage_passthru              = True
    self.use_vmfs_datastore            = False
    self.use_vmdk_svm_disk             = False
    self.use_ten_gig_only              = False   # Deprecated, use vswitches
    self.network_devices               = []
    self.fio_detected                  = False
    self.installer_path                = None
    self.factory_iso_path              = None
    self.factory_iso_size              = None
    self.factory_iso_offset            = None
    self.hyp_image_path                = None
    self.bootbank                      = None
    self.vibs                          = []
    self.hyperv_binaries               = None
    self.rpms                          = []
    self.driver_package                = None
    self.driver_config                 = None
    self.phoenix_version               = PHOENIX_VERSION
    self.foundation_version            = "unknown"
    self.foundation_ip                 = None
    self.hypervisor_hostname           = None
    self.skip_hypervisor               = False
    self.cvm_vlan_id                   = 0
    self.factory_megaraid_adapter      = None  # Factory env - internal
    self.factory_hyp_lun_label         = None  # Factory env
    self.factory_hyp_lun_index         = None  # Factory env - internal
    self.factory_lun_label             = None  # Factory env
    self.factory_lun_index             = None  # Factory env - internal
    self.factory_phoenix_lun_label     = None  # Factory env
    self.factory_phoenix_lun_index     = None  # Factory env - internal
    self.factory_error_flag_file       = None  # Factory env
    self.factory_success_flag_file     = None  # Factory env
    self.factory_logfile_info          = None  # Factory env
    self.factory_logfile_error         = None  # Factory env
    self.factory_hyp_image             = None  # Factory env
    self.factory_run_level             = 0     # Factory env
    self.factory_folder                = None  # Factory env
    self.megaraid_boot_device          = True  # Factory env
    self.factory_partition_label       = None  # Factory env
    self.factory_hypervisors_location  = []
    self.factory_drivers_location      = []
    self.ce_hyp_boot_disk              = None  # Used by Community Edition
    self.ce_cvm_boot_disks             = []    # Used by Community Edition
    self.ce_cvm_data_disks             = []    # Used by Community Edition
    self.ce_eula_accepted              = False # Used by Community Edition
    self.ce_eula_viewed                = False # Used by Community Edition
    self.create_1node_cluster          = False # Used by Community Edition
    self.ce_disks                      = []    # Used by Community Edition
    self.esx_path                      = ""    # Used by Community Edition
    self.ce_serials                    = []    # Used by Community Edition
    self.ce_wwns                       = []    # Used by Community Edition
    self.passthru_devs                 = []    # Used by Community Edition
    self.per_node_ntp_servers          = (",").join(NTP_SERVERS)
    self.hw_layout                     = None
    self.vpd_method                    = None
    self.use_hugetlbfs                 = False # Enables hugetlbfs on AHV
    self.foundation_payload            = None
    self.host_backplane_ip             = None
    self.passthru_nvme_devices         = []
    self.exclude_boot_serial           = None
    self.eos_metadata                  = None
    self.compute_only                  = False
    self.passthru_nics                 = []
    self.rdma_passthrough              = False # Enables rdma passthrough
    self.rdma_mac_addr                 = None # Specifes nic to be used for rdma
    self.rdma_port_passthrough         = False # Enables rdma port passthrough
    self.hyperv_external_vswitch       = None
    self.hyperv_external_vswitch_alias = None
    self.hyperv_sku                    = None
    self.hook_scripts                  = {}  # Enables custom hooks in PXE
    self.custom_ahv_kernel             = None  # custom kernels for dev/qual
    self.custom_linux_kernel           = None
    self.custom_cvm_kernel             = None
    self.http_proxy                    = []
    self.is_secureboot                 = None
    # is_factory will be set for NX factory workflows. Other factories
    # can use this parameter if needed.
    self.is_factory                    = False
    # Detect all PCI devices and collect network interfaces
    self.network_devices = net_info.detect_network_interfaces()
    # Detect FIO cards
    self.fio_detected = sysUtil.detect_fio_card()
    self.hyp_installed_in_vm         = False    # Foundation vm install
    self.svm_rescue_args             = []
    self.pmem                        = {}  # PMEM settings.
    self.hyperv_driver_spec_enabled  = False # Flag to control hyperv driver spec support.
    # Hypervisor licenses that may be applied during imaging.
    self.hypervisor_licenses         = []
    # UCS fabric interconnects are being used or not.
    self.ucs_fabric_interconnect_enabled = False
    self.cvm_config                  = {}
    self.cvm_devices                 = {}
    self.enable_ipv6                 = False
    self.foundation_ipv6_address     = None

  def __str__(self):
    s = ""
    for key, value in six.iteritems(self.__dict__):
      s += "%s: %s\n" % (key, value)
    return s

  def dump_json(self):
    return json.dumps(vars(self), indent=2)

  def validate(self):
    error = False

    if self.hyp_type.lower() == "esx":
      if not self.hypervisor_iso_path and not self.hyp_version:
        ERROR("Please supply 'hyp_version' for hypervisor type '%s'"
              % self.hyp_type)
        error = True

    if not self.model:
      ERROR("Please supply a 'Model'...")
      error = True
    else:
      self.model = sysUtil.sanitize_model(self.model)

    if not self.block_id:
      ERROR("Please supply a 'Block ID'...")
      error = True
    non_alpha = set(re.findall(r'[\W]+', self.block_id))
    non_alpha.discard('-')  # Allow hyphens in case UUIDs are used
    if non_alpha:
      ERROR("'Block ID' cannot contain non-alphanumeric characters except "
            "'-' and '_'")
      error = True

    if not self.node_serial:
      ERROR("Please supply 'Node Serial'...")
      error = True
    non_alpha = set(re.findall(r'[\W]+', self.node_serial))
    non_alpha.discard('-')  # Allow hyphens in case UUIDs are used
    if non_alpha:
      ERROR("'Node Serial' cannot contain non-alphanumeric characters except "
            "'-' and '_'")
      error = True

    if not self.node_position or not self.node_position.strip():
      ERROR("Please supply a 'Node Position'...")
      error = True
    else:
      self.node_position = str(self.node_position)

    if not self.node_name:
      self.node_name = "%s-%s" % (self.block_id, self.node_position)

    try:
      self.cluster_id = int(self.cluster_id)
      assert self.cluster_id > 0
    except (ValueError, AssertionError):
      ERROR("'Cluster ID' must be a positive integer...")
      error = True

    if not self.svm_install_type and not self.hyp_install_type:
      ERROR('You must make a selection of hypervisor or '
            'Svm to be imaged...')
      error = True

    if self.svm_install_type and self.compute_only:
      ERROR("You have specified a compute-only installation, but you have "
        "also set svm_install_type to %s. svm_install_type must be None for "
        "compute-only installations." % self.svm_install_type)
      error = True

    if self.compute_only and self.hyp_type.lower() != "kvm":
      message = ""
      if not features.is_enabled("esx_compute_only"):
        message = "Compute-only installation is supported only on AHV."
      elif self.hyp_type.lower() != "esx":
        message = ("Compute-only installation is supported"
                   "on AHV and ESXi.")

      if message:
        ERROR(message)
        error = True

    if self.compute_only and self.hyp_install_type != "clean":
      ERROR("Compute-only installation must be done with hyp_install_type "
        "'clean' rather than %s." % self.hyp_install_type)
      error = True

    if self.compute_only and self.create_1node_cluster:
      ERROR("Compute-only nodes cannot be used to form a cluster, but you "
        "have chosen to create a one-node cluster.")
      error = True

    if (self.hyp_type.lower() == "esx" and re.match(r"NX-2.*", self.model)):
      if not self.hyp_install_type:
        ERROR("Please select a hypervisor imaging method")
        error = True
      if not self.svm_install_type:
        ERROR("Please select a SVM imaging method")
        error = True

    if self.svm_install_type and not self.installer_path:
      ERROR("Please supply a path to the installer package...")
      error = True

    if self.svm_gb_ram:
      try:
        self.svm_gb_ram = int(self.svm_gb_ram)
        assert self.svm_gb_ram > 0
      except (ValueError, AssertionError):
        ERROR("'SVM GB RAM' (%s) must be a positive integer..." %
              self.svm_gb_ram)
        error = True

    if self.svm_num_vcpus:
      try:
        self.svm_num_vcpus = int(self.svm_num_vcpus)
        assert self.svm_num_vcpus > 0
      except (ValueError, AssertionError):
        ERROR("'SVM num vCPUs' (%s) must be a positive integer..." %
              self.svm_num_vcpus)
        error = True

    if (self.hyp_type.lower() == "hyperv" and
        features.is_enabled(features.HYPERV_DRIVER_SPEC)):
      self.hyperv_driver_spec_enabled = True

    def validate_sd_card_location_spec(attribute):
      """
      Valid example:
      [
        {
          "volume_label": "sdcard1",
          "path": "some_dir"
        },
        {
          "volume_label": "sdcard2",
          "path": "some_dir2"
        }
      ]
      """
      required_keys = ["volume_label", "path"]
      location_list = getattr(self, attribute)
      for location in location_list:
        if not all(key in list(location.keys()) for key in required_keys):
          ERROR("All elements of %s must have keys %s" %
                (attribute, required_keys))
          return False
      return True

    if self.factory_hypervisors_location:
      if not validate_sd_card_location_spec("factory_hypervisors_location"):
        error = True

    if self.factory_drivers_location:
      if not validate_sd_card_location_spec("factory_drivers_location"):
        error = True

    if 'COMMUNITY_EDITION' in os.environ:
      error = self.ce_validate() or error

    if not self.validate_hypervisor_license():
      error = True

    if error:
      raise ValidationError()


  def validate_hypervisor_license(self):
    if self.hypervisor_licenses:
      message = ""
      SUPPORTED_HYPERVISOR_FOR_LICENSING = ('esx', )

      # This shall make sure to error out when licensing is requested
      # for those hypervisors that are not implemented/supported yet.
      # It should not silently discard request of license application
      # (and potentially go noncompliant).
      if self.hyp_type.lower() not in SUPPORTED_HYPERVISOR_FOR_LICENSING:
        ERROR("Hypervisor licensing is not supported "
                   "with %s" % self.hyp_type)
        return False

      # Take care of feature flag, for each hypervisor as it gets
      # supported.
      if (self.hyp_type.lower() == 'esx' and
          not features.is_enabled(features.ESXI_LICENSING)):
        ERROR("ESX licensing feature is not enabled")
        return False

    return True


  @staticmethod
  def is_valid_ip(ip):
    m = re.match(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", ip)
    return bool(m) and all([0 <= int(n) <= 255 for n in m.groups()])

  def ce_validate(self):
    """
    Extra validation for CE.
    """
    error = False

    if len(self.host_ip) == 0:
      self.host_ip = None
    if len(self.host_subnet_mask) == 0:
      self.host_subnet_mask = None
    if len(self.default_gw) == 0:
      self.default_gw = None
    if len(self.svm_ip) == 0:
      self.svm_ip = None
    if len(self.svm_subnet_mask) == 0:
      self.svm_subnet_mask = None
    if len(self.svm_default_gw) == 0:
      self.svm_default_gw = None

    if ((self.host_ip or self.host_subnet_mask or self.default_gw) and not
        (self.host_ip and self.host_subnet_mask and self.default_gw)):
      ERROR("If any of the host network information is supplied,"
            " all three fields must be filled.")
      error = True

    if ((self.svm_ip or self.svm_subnet_mask or self.svm_default_gw) and not
        (self.svm_ip and self.svm_subnet_mask and self.svm_default_gw)):
      ERROR("If any of the CVM network information is supplied,"
            " all three fields must be filled.")
      error = True

    if self.host_ip and not self.is_valid_ip(self.host_ip):
      ERROR("Host IP is malformed.")
      error = True

    if self.host_ip and self.host_ip.startswith('192.168.5.'):
      ERROR("Host IP cannot be in the 192.168.5.x network.")
      error = True

    if self.host_subnet_mask and not self.is_valid_ip(self.host_subnet_mask):
      ERROR("Host Subnet Mask is malformed.")
      error = True

    if self.default_gw and not self.is_valid_ip(self.default_gw):
      ERROR("Host Gateway is malformed.")
      error = True

    if self.svm_ip and not self.is_valid_ip(self.svm_ip):
      ERROR("CVM IP is malformed.")
      error = True

    if self.svm_ip and self.svm_ip.startswith('192.168.5.'):
      ERROR("CVM IP cannot be in the 192.168.5.x network.")
      error = True

    if self.svm_subnet_mask and not self.is_valid_ip(self.svm_subnet_mask):
      ERROR("CVM Subnet Mask is malformed.")
      error = True

    if self.svm_default_gw and not self.is_valid_ip(self.svm_default_gw):
      ERROR("CVM Gateway is malformed.")
      error = True

    if self.create_1node_cluster:
      if self.dns_ip and not self.is_valid_ip(self.dns_ip):
        ERROR("DNS Server IP is malformed.")
        error = True

    if not self.ce_eula_accepted:
      ERROR("The installation cannot proceed if you do not accept the End "
            "User License Agreement.")
      error = True

    if not self.ce_eula_viewed:
      ERROR("The installation cannot proceed if you do not scroll to the end "
            "of the End User License Agreement.")
      error = True

    return error

  def get_factory_config(self):
    """
    Both CVM installation and compute-only host installation want the factory
    configuration, so maintain its creation here to keep them in sync.
    """
    factory_config = {
        "node_serial": self.node_serial,
        "rackable_unit_serial": self.block_id,
        "node_position": self.node_position,
        "cluster_id": self.cluster_id,
        "rackable_unit_model": self.model,
    }

    if self.node_uuid:
      factory_config["node_uuid"] = self.node_uuid

    return factory_config

  @property
  def enable_rdma_passthrough(self):
    return self.rdma_passthrough or self.rdma_mac_addr is not None