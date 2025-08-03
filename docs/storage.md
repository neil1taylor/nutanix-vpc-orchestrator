# Storage

Nutanix uses a **Controller Virtual Machine (CVM)** to handle all storage I/O for workload VMs. Let me explain how this unique architecture works:

## 🏗️ **Nutanix Storage Architecture Overview**

### **The Controller VM (CVM) - The "Brain"**
The Nutanix Controller Virtual Machine (CVM) is a specialized virtual machine deployed on every node within a Nutanix cluster. Its purpose is to provide all core Nutanix services—storage, cluster management, data protection, replication, and more. Without the CVM, a Nutanix node cannot operate as part of the cluster.

The CVM runs as a virtual machine on each node but manages all the physical storage devices on that node. The CVM itself is typically quite small (usually 32GB RAM, 4-8 vCPUs, and minimal disk space). The CVM uses a small amount of storage for its OS, logs, and metadata.

All NVMe drives (along with SSDs and HDDs if present) in the host node are added to the unified storage pool. Storage is presented to user VMs through the CVM via NFS, iSCSI, or SMB protocols.

By running as a VM in user-space it decouples the Nutanix software from the underlying hypervisor and hardware platforms. This enabled us to rapidly add support for other hypervisors while keeping the core code base the same across all operating environments.

## 📊 **Storage I/O Path - How Data Flows**

### **VM to CVM to Storage**
Here's exactly how storage I/O works:

1. **Workload VM writes data** → Hypervisor (AHV/ESXi/Hyper-V)
2. **Hypervisor** → Routes I/O to local CVM via iSCSI/NFS/SMB
3. **CVM processes I/O** → Stargate service handles all storage operations
4. **CVM writes to physical storage** → Direct access to NVMe/SSD/HDD drives

### **Key Component: Stargate Service**
Within the CVM the Stargate process is responsible for handling all I/O coming from user VMs (UVMs) and persistence (RF, etc.). When a write request comes to Stargate, there is a write characterizer which will determine if the write gets persisted to the OpLog for bursty random writes, or to Extent Store for sustained random and sequential writes.

A distributed system that presents storage to other systems (such as a hypervisor) needs a unified component for receiving and processing data that it receives. The Nutanix cluster has a large software component called Stargate that manages this responsibility. From the perspective of the hypervisor, Stargate is the main point of contact for the Nutanix cluster.

## 🔌 **How CVMs Access Physical Storage**

### **Direct Hardware Access**
The main thing that most of you are familiar with already, is that the LSI controller is passed directly to the CVM in order for it to have direct access to the disks in the node.

For the Nutanix units running VMware vSphere, the SCSI controller, which manages the SSD and HDD devices, is directly passed to the CVM leveraging VM-Direct Path (Intel VT-d). In the case of Hyper-V, the storage devices are passed through to the CVM.

### **VM to CVM Communication**
On AHV the disks are actually mounted as iSCSI to VMs (target of that iSCSI is CVM stargate service) When the VMs write the data, the IO is interfaced to stargate in CVM, then the magic happens there (IO optimization, coalescence, compression, deduplication, RF, EC-X, etc) The CVM writes the data to Physical Media (NVME, SSD, HDD) directly as the HBA/Disk controller/NVMe disks are mounted to CVM as passthrough.

## 🚀 **Data Locality & Performance**

### **Local I/O Optimization**
Being a converged (compute+storage) platform, I/O and data locality are critical to cluster and VM performance with Nutanix. As explained above in the I/O path, all read/write IOs are served by the local Controller VM (CVM) which is on each hypervisor adjacent to normal VMs.

Because Nutanix is a converged (compute + storage) platform, data locality and I/O are essential to cluster and VM performance. The local controller VM (CVM) on each hypervisor next to regular VMs serves all read/write IOs. Data for a VM is controlled by the CVM and served locally from disks inside the node.

### **Remote I/O When Needed**
For all read requests, these will be served completely locally in most cases and never touch the 10GbE network. This means that the only traffic touching the public 10GbE network will be AOS remote replication traffic and VM network I/O. There will, however, be cases where the CVM will forward requests to other CVMs in the cluster in the case of a CVM being down or data being remote.

## 🔧 **Why This Architecture Works**

### **Benefits of VM-Based Storage Controller**
The key reasons for running the Nutanix controllers as VMs in user-space really come down to four core areas: By running as a VM in user-space it decouples the Nutanix software from the underlying hypervisor and hardware platforms. This enabled us to rapidly add support for other hypervisors while keeping the core code base the same across all operating environments. Additionally, it gave us flexibility to not be bound to vendor specific release cycles.

### **Resilience & Upgrades**
Due to the nature of running as a VM in user-space, we can elegantly handle things like upgrades or CVM "failures" as they are outside of the hypervisor. For example, if there is some catastrophic issue where a CVM goes down, the whole node still continues to operate with storage I/Os and services coming from other CVMs in the cluster. During a AOS (Nutanix Core Software) upgrade, we can reboot the CVM without any impact to the workloads running on that host.

## 📋 **Key Storage Components in CVM**

1. **Stargate**: Main storage I/O processor
2. **Medusa**: Metadata management 
3. **Cassandra**: Distributed metadata database
4. **Zeus**: Cluster configuration management
5. **Curator**: Background storage optimization

## 🔄 **Storage Flow Summary**

```
Workload VM → Hypervisor → CVM (Stargate) → Physical Storage
     ↑                                              ↓
     └── Storage presented via iSCSI/NFS/SMB ←──────┘
```

The CVM acts as an intelligent storage controller that:
- **Receives** all I/O from workload VMs
- **Processes** data (compression, dedup, replication)
- **Distributes** data across cluster for redundancy
- **Optimizes** performance with local caching
- **Presents** unified storage back to hypervisor

This architecture gives Nutanix the benefits of both local storage performance and enterprise shared storage features, all managed through software running in VMs rather than proprietary hardware controllers.

## Foundation Storage Configuration Process

**Foundation's Role:**
Foundation is a Nutanix provided tool leveraged for bootstrapping, imaging and deployment of Nutanix clusters. The imaging process will install the desired version of the AOS software as well as the hypervisor of choice.

**Automatic Storage Pool Creation:**
When a Nutanix cluster is created, the system connects all the nodes' disks in a Storage Pool. Foundation automatically configures this during cluster creation - you don't manually configure individual drives or RAID arrays.

**Storage Architecture Requirements:**
- **JBOD Configuration Required:** You don't need a RAID configuration, but a JBOD (Just a Bunch of Disks) configuration. The control VM/AOS of Nutanix is responsibilty of the disk redundancy and the control VM needs direct access to the disks/controller.
- **Minimum Disk Requirements:** To be able to install the 3/4 nodes you need at least 2 disks in non raid (JBOD) setup:
    - One data disk.
    - One boot disk.

## Foundation Configuration Requirements

**Network Configuration:**
A typical deployment requires 3 IP addresses per node (hypervisor, CVM, remote management (e.g. IPMI, iDRAC, etc.)). In addition to the per node addresses, it is recommended to set a Cluster and Data Services IP addresses.

**Foundation Setup Process:**
1. **Discovery:** Foundation discovers un-configured nodes on the network
2. **Node Selection:** Select nodes to form the cluster
3. **Network Configuration:** Input cluster details and IP addresses for each component
4. **Network Validation:** Foundation validates IP conflicts and connectivity
5. **Image Selection:** Choose AOS version and hypervisor (if different from default AHV)
6. **Automatic Configuration:** Foundation automatically creates the storage pool from all available drives

**Key Points:**
- Foundation automatically pools all drives (NVMe, SSD, HDD) into a single distributed storage pool
- No manual storage configuration is needed - Foundation handles this automatically
- The hardware controller must be set to JBOD mode, not RAID
- It is not recommended to have multiple Storage Pools.
- Storage containers are created post-deployment for organizing workloads within the storage pool

Foundation essentially abstracts away the complexity of storage configuration, automatically creating the distributed storage fabric that spans all nodes in the cluster.