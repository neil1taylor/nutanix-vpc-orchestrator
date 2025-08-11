"""
Server Profile Storage Configuration Mapping
"""

class ServerProfileConfig:
    """
    Server profile configurations for IBM Cloud VPC Bare Metal servers
    Maps server profiles to their storage and compute specifications
    """
    
    # Server profile storage configurations
    SERVER_PROFILES = {
        # Generation 2 Balanced profiles with local storage (d suffix)
        'bx2d-metal-24x96': {
            'display_name': 'Balanced Gen2 - 24 vCPU, 96 GB RAM, NVMe Storage',
            'cpu_cores': 12,  # Physical cores (24 vCPU / 2)
            'memory_gb': 96,
            'boot_drives': ['nvme0n1'],  # RAID1 SATA M.2 drives
            'boot_drive_size': '960GB',
            'data_drives': ['nvme1n1', 'nvme2n1', 'nvme3n1', 'nvme4n1', 'nvme5n1', 'nvme6n1', 'nvme7n1', 'nvme8n1'],
            'data_drive_size': '3.2TB',
            'data_drive_count': 8,
            'network_interfaces': ['eth0', 'eth1'],
            'recommended_cluster_role': 'compute-storage',
            'generation': 'gen2'
        },
        'bx2d-metal-48x192': {
            'display_name': 'Balanced Gen2 - 48 vCPU, 192 GB RAM, NVMe Storage',
            'cpu_cores': 24,
            'memory_gb': 192,
            'boot_drives': ['nvme0n1'],
            'boot_drive_size': '960GB',
            'data_drives': ['nvme1n1', 'nvme2n1', 'nvme3n1', 'nvme4n1', 'nvme5n1', 'nvme6n1', 'nvme7n1', 'nvme8n1'],
            'data_drive_size': '3.2TB',
            'data_drive_count': 8,
            'network_interfaces': ['eth0', 'eth1'],
            'recommended_cluster_role': 'compute-storage',
            'generation': 'gen2'
        },
        'bx2d-metal-96x384': {
            'display_name': 'Balanced Gen2 - 96 vCPU, 384 GB RAM, NVMe Storage',
            'cpu_cores': 48,
            'memory_gb': 384,
            'boot_drives': ['nvme0n1'],
            'boot_drive_size': '960GB',
            'data_drives': ['nvme1n1', 'nvme2n1', 'nvme3n1', 'nvme4n1', 'nvme5n1', 'nvme6n1', 'nvme7n1', 'nvme8n1'],
            'data_drive_size': '3.2TB',
            'data_drive_count': 8,
            'network_interfaces': ['eth0', 'eth1'],
            'recommended_cluster_role': 'compute-storage',
            'generation': 'gen2'
        },
        
        # Generation 3 Compute profiles with local storage (x3d suffix)
        'cx3d-metal-48x128': {
            'display_name': 'Compute Gen3 - 48 vCPU, 128 GB RAM, NVMe Storage',
            'cpu_cores': 24,
            'memory_gb': 128,
            'boot_drives': ['nvme0n1'],
            'boot_drive_size': '960GB',
            'data_drives': ['nvme1n1', 'nvme2n1', 'nvme3n1', 'nvme4n1'],
            'data_drive_size': '3.2TB',
            'data_drive_count': 8,
            'network_interfaces': ['eth0', 'eth1'],
            'recommended_cluster_role': 'compute-storage',
            'generation': 'gen3'
        },
        'cx3d-metal-64x128': {
            'display_name': 'Compute Gen3 - 64 vCPU, 128 GB RAM, NVMe Storage',
            'cpu_cores': 32,
            'memory_gb': 128,
            'boot_drives': ['nvme0n1'],
            'boot_drive_size': '960GB',
            'data_drives': ['nvme1n1', 'nvme2n1', 'nvme3n1', 'nvme4n1', 'nvme5n1', 'nvme6n1', 'nvme7n1', 'nvme8n1'],
            'data_drive_size': '3.2TB',
            'data_drive_count': 8,
            'network_interfaces': ['eth0', 'eth1'],
            'recommended_cluster_role': 'compute-storage',
            'generation': 'gen3'
        },
        
        # Generation 3 Balanced profiles with local storage (x3d suffix)
        'bx3d-metal-48x256': {
            'display_name': 'Balanced Gen3 - 48 vCPU, 256 GB RAM, NVMe Storage',
            'cpu_cores': 24,
            'memory_gb': 256,
            'boot_drives': ['nvme0n1'],
            'boot_drive_size': '960GB',
            'data_drives': ['nvme1n1', 'nvme2n1', 'nvme3n1', 'nvme4n1', 'nvme5n1', 'nvme6n1', 'nvme7n1'],
            'data_drive_size': '3.2TB',
            'data_drive_count': 8,
            'network_interfaces': ['eth0', 'eth1'],
            'recommended_cluster_role': 'compute-storage',
            'generation': 'gen3'
        },
        'bx3d-metal-64x256': {
            'display_name': 'Balanced Gen3 - 64 vCPU, 256 GB RAM, NVMe Storage',
            'cpu_cores': 32,
            'memory_gb': 256,
            'boot_drives': ['nvme0n1'],
            'boot_drive_size': '960GB',
            'data_drives': ['nvme1n1', 'nvme2n1', 'nvme3n1', 'nvme4n1', 'nvme5n1', 'nvme6n1', 'nvme7n1', 'nvme8n1'],
            'data_drive_size': '3.2TB',
            'data_drive_count': 8,
            'network_interfaces': ['eth0', 'eth1'],
            'recommended_cluster_role': 'compute-storage',
            'generation': 'gen3'
        },
        
        # Memory profiles with local storage (x3d suffix)
        'mx3d-metal-16x128': {
            'display_name': 'Memory Gen3 - 16 vCPU, 128 GB RAM, NVMe Storage',
            'cpu_cores': 8,
            'memory_gb': 128,
            'boot_drives': ['nvme0n1'],
            'boot_drive_size': '960GB',
            'data_drives': ['nvme1n1', 'nvme2n1', 'nvme3n1'],  # Fewer drives for memory-optimized
            'data_drive_size': '3.2TB',
            'data_drive_count': 4,
            'network_interfaces': ['eth0', 'eth1'],
            'recommended_cluster_role': 'storage',  # Good for storage-heavy workloads
            'generation': 'gen3'
        },
        
        # Ultra High Memory profiles with local storage (x3d suffix)
        'vx3d-metal-16x256': {
            'display_name': 'Very High Memory Gen3 - 16 vCPU, 256 GB RAM, NVMe Storage',
            'cpu_cores': 8,
            'memory_gb': 256,
            'boot_drives': ['nvme0n1'],
            'boot_drive_size': '960GB',
            'data_drives': ['nvme1n1', 'nvme2n1', 'nvme3n1'],
            'data_drive_size': '3.2TB',
            'data_drive_count': 4,
            'network_interfaces': ['eth0', 'eth1'],
            'recommended_cluster_role': 'storage',
            'generation': 'gen3'
        }
    }
    
    # Storage configuration templates based on use case
    STORAGE_TEMPLATES = {
        'nutanix_default': {
            'description': 'Default Nutanix configuration - all NVMe drives for storage pool',
            'boot_device': '/dev/sda',           # First boot drive
            'hypervisor_device': '/dev/sda',     # AHV shares boot device
            'cvm_device': '/dev/sda',            # CVM shares boot device
            'exclude_drives': 0,                 # Use all available data drives
            'raid_config': 'nutanix_managed'     # Let Nutanix handle RAID
        },
        'nutanix_reserved': {
            'description': 'Reserve last drive for future expansion',
            'boot_device': '/dev/sda',
            'hypervisor_device': '/dev/sda', 
            'cvm_device': '/dev/sda',
            'exclude_drives': 1,                 # Reserve last drive
            'raid_config': 'nutanix_managed'
        },
        'nutanix_performance': {
            'description': 'Optimize for performance - use subset of fastest drives',
            'boot_device': '/dev/sda',
            'hypervisor_device': '/dev/sda',
            'cvm_device': '/dev/sda', 
            'exclude_drives': 2,                 # Use 6 of 8 drives for better performance
            'raid_config': 'nutanix_managed'
        }
    }
    
    @classmethod
    def get_profile_config(cls, server_profile):
        """Get configuration for a specific server profile"""
        return cls.SERVER_PROFILES.get(server_profile)
    
    @classmethod
    def get_storage_config(cls, server_profile, template='nutanix_default'):
        """
        Generate storage configuration for a server profile
        
        Args:
            server_profile: IBM Cloud server profile name
            template: Storage template to use
            
        Returns:
            Dict with storage configuration
        """
        profile_config = cls.get_profile_config(server_profile)
        storage_template = cls.STORAGE_TEMPLATES.get(template, cls.STORAGE_TEMPLATES['nutanix_default'])
        
        if not profile_config:
            raise ValueError(f"Unknown server profile: {server_profile}")
        
        # Calculate which drives to use
        available_drives = profile_config['data_drives']
        exclude_count = storage_template['exclude_drives']
        data_drives = available_drives[:-exclude_count] if exclude_count > 0 else available_drives
        
        return {
            'server_profile': server_profile,
            'template': template,
            'boot_device': storage_template['boot_device'],
            'hypervisor_device': storage_template['hypervisor_device'],
            'cvm_device': storage_template['cvm_device'],
            'data_drives': data_drives,
            'total_drives': len(available_drives),
            'drives_used': len(data_drives),
            'drives_reserved': exclude_count,
            'raid_config': storage_template['raid_config'],
            'drive_info': {
                'boot_drive_size': profile_config['boot_drive_size'],
                'data_drive_size': profile_config['data_drive_size'],
                'total_storage_capacity': f"{len(data_drives) * 3.2:.1f}TB"
            }
        }
    
    @classmethod
    def get_recommended_cluster_role(cls, server_profile):
        """Get recommended cluster role for a server profile"""
        profile_config = cls.get_profile_config(server_profile)
        return profile_config['recommended_cluster_role'] if profile_config else 'compute-storage'
    
    @classmethod
    def get_available_profiles(cls):
        """Get list of available server profiles with descriptions"""
        profiles = []
        for profile_name, config in cls.SERVER_PROFILES.items():
            profiles.append({
                'name': profile_name,
                'display_name': config['display_name'],
                'cpu_cores': config['cpu_cores'],
                'memory_gb': config['memory_gb'],
                'storage_capacity': f"{config['data_drive_count'] * 3.2:.1f}TB",
                'recommended_role': config['recommended_cluster_role'],
                'generation': config['generation']
            })
        return sorted(profiles, key=lambda x: (x['generation'], x['cpu_cores']))
    
    @classmethod
    def validate_profile(cls, server_profile):
        """Validate if server profile is supported"""
        return server_profile in cls.SERVER_PROFILES
    
    @classmethod
    def get_profile_summary(cls, server_profile):
        """Get a summary of the server profile capabilities"""
        config = cls.get_profile_config(server_profile)
        if not config:
            return None
        
        return {
            'profile': server_profile,
            'display_name': config['display_name'],
            'compute': {
                'cpu_cores': config['cpu_cores'],
                'memory_gb': config['memory_gb']
            },
            'storage': {
                'boot_drives': len(config['boot_drives']),
                'boot_capacity': config['boot_drive_size'],
                'data_drives': len(config['data_drives']),
                'data_capacity_per_drive': config['data_drive_size'],
                'total_data_capacity': f"{len(config['data_drives']) * 3.2:.1f}TB"
            },
            'networking': {
                'interfaces': len(config['network_interfaces'])
            },
            'nutanix': {
                'recommended_role': config['recommended_cluster_role'],
                'suitable_for': cls._get_suitability(config)
            }
        }
    
    @classmethod
    def _get_suitability(cls, config):
        """Determine what workloads this profile is suitable for"""
        suitability = []
        
        if config['cpu_cores'] >= 24 and config['memory_gb'] >= 192:
            suitability.append('Large-scale virtualization')
        if config['cpu_cores'] >= 16:
            suitability.append('High-performance computing')
        if config['memory_gb'] >= 256:
            suitability.append('Memory-intensive applications')
        if config['data_drive_count'] >= 6:
            suitability.append('Storage-heavy workloads')
        if config['recommended_cluster_role'] == 'compute-storage':
            suitability.append('Nutanix HCI clusters')
        
        return suitability if suitability else ['General purpose workloads']