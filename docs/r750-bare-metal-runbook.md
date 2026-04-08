# Dell PowerEdge R750 — Bare Metal Ubuntu 24.04 LTS Installation Runbook

**Hardware:** 2x Xeon Silver 4310, 813GB DDR4, PERC H755 (9x 1.2TB SAS RAID 5), BOSS M.2 240GB RAID 1, iDRAC9 Enterprise, no GPU
**Goal:** Wipe Windows Server / Hyper-V, install Ubuntu 24.04 minimal server, configure for CPU-only LLM inference with dual NUMA-pinned Ollama instances.

---

## Part 1: Pre-Install Preparation (iDRAC)

### 1.1 Access iDRAC

Connect to `https://<idrac-ip>` in a browser. Default credentials are on the pull-out tag on the front of the server (usually `root` / the tag password). If you have already changed them, use those.

> **Warning:** iDRAC9's HTML5 console works best in Chrome or Edge. Firefox has intermittent issues with virtual media and keyboard passthrough.

### 1.2 Verify DIMM Layout

Navigate to **Configuration > Memory Settings** (or **System > Memory** depending on firmware version).

You need to verify balanced population across sockets and channels. The R750 has 16 DIMM slots per socket (32 total). With 813GB across 16 DIMMs, you likely have a mix — probably 12x 64GB + 4x 16GB, or some similar combination that totals ~813GB (which is unusual; this may actually be reported as 768GB usable with ECC overhead, or you may have 16x 64GB = 1024GB with some DIMMs reporting reduced capacity).

**What to check:**

- Go to **System > Overview > Memory** or **System > Inventory > Memory**
- Confirm DIMMs are populated symmetrically: each socket should have the same number of DIMMs
- For best bandwidth: DIMMs should be spread across all 8 channels per socket (the R750 has 8 memory channels per CPU). Populate channels A through H before doubling up on any channel.
- The iDRAC memory page will show each DIMM slot (A1, A2, B1, B2, etc.), its size, speed, and channel.

**Ideal for your config (16 DIMMs, 2 sockets):** 8 DIMMs per socket, one per channel. This gives you full 8-channel bandwidth on both sockets — the best possible config for memory-bound LLM inference.

If DIMMs are clustered (e.g., 12 in one socket, 4 in the other), you will get asymmetric NUMA performance. Reseating DIMMs for balance is strongly recommended before proceeding.

### 1.3 BIOS Settings for LLM Inference

Navigate to **Configuration > BIOS Settings**. You can also press **F2** during POST to enter BIOS setup directly via the virtual console, but iDRAC's web UI is easier.

Change these settings:

| Setting | Location in BIOS | Value | Why |
|---|---|---|---|
| **Boot Mode** | Boot Settings | UEFI | Required for modern Ubuntu, GPT partitioning |
| **Secure Boot** | Boot Settings > Secure Boot | **Disabled** | Ubuntu 24.04 supports Secure Boot, but disabling avoids issues with unsigned kernel modules, custom DKMS drivers, etc. You can re-enable later if needed. |
| **System Profile** | System BIOS > System Profile Settings | **Performance** | Locks CPUs at max frequency, disables deep idle states |
| **C-States** | System BIOS > System Profile Settings > CPU Power Management | **C1 only** (or Disabled) | Deep C-states (C6, C1E) cause latency spikes when cores wake up during inference. C1 is acceptable — it halts the core but keeps it instantly available. |
| **C1E** | Same section | **Disabled** | C1E is an enhanced idle that drops voltage; disable it for consistent latency. |
| **Logical Processor (Hyperthreading)** | System BIOS > Processor Settings | **Disabled** | Community consensus for CPU-only LLM inference: HT hurts throughput. Two logical threads competing for the same core's execution units, cache, and memory bandwidth degrades inference. You want 12 real cores per socket, not 24 virtual. With HT off, `OLLAMA_NUM_THREAD=12` maps cleanly to physical cores. |
| **Sub-NUMA Clustering (SNC)** | System BIOS > Processor Settings | **Disabled** | SNC splits each socket into 2 sub-NUMA domains (giving you 4 NUMA nodes instead of 2). This complicates memory binding for Ollama and splits your per-socket RAM in half per domain. Keep it simple: 2 nodes. |
| **Virtualization Technology** | System BIOS > Processor Settings | **Disabled** | You are not running VMs. Disabling removes a small overhead. |
| **NUMA Optimization** | System BIOS > Processor Settings | **Enabled** (should be default) | Ensures the OS sees proper NUMA topology. |
| **Memory Operating Mode** | System BIOS > Memory Settings | **Optimizer Mode** | Maximizes bandwidth and capacity. Do not use Mirror or Spare mode — those reduce usable RAM. |

After changing, click **Apply** and note that changes take effect on next reboot.

### 1.4 Set Boot Order

Navigate to **Configuration > BIOS Settings > Boot Settings > UEFI Boot Sequence**.

- Move **BOSS M.2** (it will appear as something like `AHCI: DELL BOSS-N1 Modular` or `BOSS-S2`) to the **first** position
- Move the PERC H755 virtual disk down or remove it from the boot sequence entirely — you do not want to accidentally boot from the data array

### 1.5 Configure BOSS M.2 RAID 1

The BOSS (Boot Optimized Server Storage) controller is a separate hardware RAID controller for the two M.2 sticks. It should already be configured as RAID 1 if Dell set it up at the factory.

**Verify via iDRAC:** Go to **Storage > Controllers** and find the BOSS controller. Confirm:
- Two M.2 drives are present
- They are in a RAID 1 (mirror) virtual disk
- Status is "Ready" or "Online"

If not configured, you can create the RAID 1 from the **Dell BOSS Configuration Utility** (accessible during POST via Ctrl+B, or from iDRAC's storage configuration page). Select both M.2 drives and create a RAID 1 virtual disk.

> **Warning:** The BOSS M.2 240GB drives are SATA, not NVMe. Performance is adequate for an OS boot drive but not spectacular. This is fine — your working data lives on the PERC array.

### 1.6 Verify PERC H755 RAID 5 Array

Navigate to **Storage > Controllers > PERC H755 Front** (or similar).

If the RAID 5 array already exists from the Windows installation:
- Note the virtual disk size (should be approximately 9.6TB usable from 9x 1.2TB with one drive of parity)
- You can either delete and recreate it, or leave it — the Ubuntu installer will format it regardless

If no virtual disk exists, create one:
1. Go to **Storage > Controllers > PERC H755 > Create Virtual Disk**
2. RAID Level: **RAID 5**
3. Select all 9 physical disks (1.2TB 10K SAS each)
4. Strip size: **256KB** (good for large sequential reads, which is what model loading does)
5. Read Policy: **Read Ahead** (improves sequential read performance)
6. Write Policy: **Write Back** with BBU (the H755 has a battery-backed cache; Write Back is safe and much faster)
7. Initialize: **Fast Initialize** is fine since you will format it during Ubuntu install

Expected usable capacity: ~8.7TB (9 drives minus 1 parity, minus formatting overhead).

### 1.7 Mount Ubuntu 24.04 ISO via Virtual Media

1. Download **Ubuntu 24.04.x LTS Server** ISO (the "live server" installer) from https://ubuntu.com/download/server — get the AMD64 version
2. In iDRAC, go to **Virtual Console** and click **Launch Virtual Console** (HTML5)
3. In the virtual console window, go to **Virtual Media > Connect Virtual Media**
4. Click **Map CD/DVD** and browse to the Ubuntu ISO on your local machine
5. Click **Map Device**

Now reboot the server: **Maintenance > Power > Reboot**. During POST, press **F11** for the one-time boot menu and select the **Virtual CD** option (it will say something like `Virtual Optical Drive`).

> **Warning:** Virtual media over iDRAC is slow — the ISO streams over the network. The installer will boot and run but expect it to take 2-3x longer than a USB stick. If you have physical access, a USB stick (burned with `dd` or Balena Etcher) plugged into the front USB port is much faster. If using USB, set it as boot priority in the one-time boot menu (F11).

---

## Part 2: Storage Configuration & Ubuntu Installation

### 2.1 Driver Compatibility

**Does Ubuntu 24.04 see the PERC H755 natively?**
Yes. The PERC H755 is based on the Broadcom MegaRAID SAS chipset and uses the `megaraid_sas` kernel driver. This driver has been in the mainline Linux kernel for years. Ubuntu 24.04 (kernel 6.8) includes it out of the box. The RAID virtual disk will appear as a standard block device (e.g., `/dev/sda` or `/dev/sdb`).

**Does Ubuntu see the BOSS M.2 controller natively?**
Yes. The BOSS-S2 (or BOSS-N1) controller presents its RAID 1 virtual disk as a standard AHCI/SATA device. It appears as a normal block device (e.g., `/dev/sda`). No special drivers are needed.

**Block device naming:** With both controllers active, you will likely see:
- `/dev/sda` — BOSS M.2 RAID 1 (240GB) — this is smaller, easy to identify
- `/dev/sdb` — PERC H755 RAID 5 (~8.7TB) — this is the large one

Verify by size during the installer. The BOSS drive is ~240GB, the PERC array is ~8.7TB. Hard to mix up.

### 2.2 Partition Scheme

**BOSS M.2 240GB (boot device):**

| Mount Point | Size | Filesystem | Notes |
|---|---|---|---|
| `/boot/efi` | 1 GB | FAT32 (EFI System Partition) | UEFI requires this. 1GB is generous but avoids ever running out of space with multiple kernels. |
| `/` | ~204 GB | ext4 | Root filesystem. Holds OS, packages, /home, /var, /tmp. 200GB is more than enough for a server. |
| swap | ~35 GB | swap | With 813GB RAM you will almost never swap. But some swap is good for emergency OOM situations and `vm.swappiness` can be set very low. Hibernation is not practical with this much RAM (would need 813GB+ swap), so this is just a safety net. |

**PERC H755 RAID 5 (~8.7TB):**

| Mount Point | Size | Filesystem | Notes |
|---|---|---|---|
| `/data` | Entire disk | **XFS** | Single partition, entire array. |

**Why XFS over ext4 for /data:**
- XFS handles large files (LLM models are 4-70GB each) better with its extent-based allocation
- XFS has superior parallel I/O performance, which matters when PostgreSQL, Redis, and Ollama are all hitting the same array
- XFS supports online growth (if you add disks to the RAID later, you can expand without unmounting)
- XFS has better performance for the `fallocate` patterns that Ollama uses when downloading models
- Downside: XFS cannot be shrunk, only grown. This is fine for a data partition you want to use all of.

### 2.3 Ubuntu Installer Walkthrough

When the ISO boots, you will see the GRUB menu. Select **"Try or Install Ubuntu Server"**.

**Step 1: Language**
Select English (or your preference). Press Enter.

**Step 2: Installer Update**
If the installer offers to update itself, choose **"Continue without updating"** — you are on virtual media and the update download will be slow. You will `apt upgrade` after install anyway.

**Step 3: Keyboard**
Select your keyboard layout. Enter.

**Step 4: Installation Type**
Select **"Ubuntu Server (minimized)"** — this gives you the smallest footprint. No desktop environment, no snaps beyond what is essential. You want minimal.

> If "minimized" is not shown, select "Ubuntu Server" — it is still a CLI-only install. The minimized option removes man pages, docs, and some utilities. Either works.

**Step 5: Network**
The installer will detect your NICs. You should see multiple interfaces:
- `eno1`, `eno2` — Broadcom 5720 onboard dual-port
- `eno3`, `eno4`, `eno5`, `eno6` (or similar) — OCP quad-port NIC

For now, let one interface get DHCP. You will configure a static IP post-install. Pick the one that is connected and showing a link (the installer shows link status). Typically `eno1` is the first onboard port.

**Step 6: Proxy**
Leave blank unless your network requires one.

**Step 7: Mirror**
Accept the default Ubuntu mirror, or change to a closer one if you know one.

**Step 8: Storage Layout — THIS IS THE CRITICAL STEP**

Select **"Custom storage layout"** (not "Use an entire disk").

You will see your two block devices. Identify them:
- The ~240GB device is your BOSS M.2 (e.g., `/dev/sda`)
- The ~8.7TB device is your PERC RAID 5 (e.g., `/dev/sdb`)

**Configure the BOSS M.2 (240GB):**

1. Select the 240GB device
2. If it has existing partitions (from Windows), delete all of them
3. Select **"Add GPT Partition Table"** (this creates a fresh GPT)
4. Add partition 1:
   - Size: **1G**
   - Format: **fat32**
   - Mount: **/boot/efi**
   - Flag it as **ESP** (EFI System Partition) — the installer usually does this automatically when you pick /boot/efi
5. Add partition 2:
   - Size: **204G**
   - Format: **ext4**
   - Mount: **/**
6. Add partition 3:
   - Size: **35G** (or "remaining" — should be approximately 35GB)
   - Format: **swap**

**Configure the PERC RAID 5 (~8.7TB):**

1. Select the ~8.7TB device
2. Delete any existing partitions
3. Add GPT Partition Table
4. Add partition 1:
   - Size: Leave as default (use all available space)
   - Format: **xfs**
   - Mount: **/data**

Review the layout summary. It should show:

```
/dev/sda1  1.0G   fat32  /boot/efi
/dev/sda2  204G   ext4   /
/dev/sda3  35G    swap
/dev/sdb1  8.7T   xfs    /data
```

> **Warning:** Double-check that the EFI partition is on the BOSS drive (the 240GB one), NOT on the PERC array. If the EFI partition is on the wrong device, the system will not boot.

Confirm and proceed. The installer will warn that this is destructive. Confirm.

**Step 9: Profile Setup**

- **Your name:** Your full name
- **Server name (hostname):** Pick something meaningful, e.g., `r750-inference` or `poweredge`
- **Username:** Your admin username (e.g., `anthony`)
- **Password:** Strong password

**Step 10: Ubuntu Pro**
Skip — select "Continue without Ubuntu Pro."

**Step 11: SSH Setup**
Select **"Install OpenSSH server"** — check this box. This is essential for remote access.

If you have a GitHub account, you can import SSH keys: select "Import SSH identity" and enter your GitHub username. The installer will pull your public keys from `https://github.com/<username>.keys`. This is convenient and means you can SSH in immediately after install.

**Step 12: Featured Server Snaps**
Do NOT install any snaps here. Skip all of them. You will install Docker and other software properly post-install.

**Step 13: Installation**
The installer runs. This takes 5-15 minutes depending on virtual media speed. Watch for errors.

When complete, select **"Reboot Now"**. The installer will prompt you to remove the installation media — go to the iDRAC virtual console, Virtual Media > Disconnect. Then press Enter to reboot.

### 2.4 First Boot

The server should boot from the BOSS M.2 into Ubuntu. Log in with the credentials you set.

Verify you are on the right device:

```bash
lsblk
```

Expected output (approximately):

```
NAME   MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
sda      8:0    0 223.6G  0 disk
├─sda1   8:1    0     1G  0 part /boot/efi
├─sda2   8:2    0   204G  0 part /
└─sda3   8:3    0    35G  0 part [SWAP]
sdb      8:16   0   8.7T  0 disk
└─sdb1   8:17   0   8.7T  0 part /data
```

If you see this, storage is correctly configured.

---

## Part 3: Post-Install Configuration

### 3.1 Update the System

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

Wait for the reboot, then SSH back in (or use the iDRAC console).

### 3.2 Install Essential Packages

```bash
sudo apt install -y \
  numactl \
  htop \
  iotop \
  sysstat \
  lm-sensors \
  pciutils \
  dmidecode \
  net-tools \
  curl \
  wget \
  git \
  build-essential \
  linux-tools-common \
  linux-tools-$(uname -r) \
  cpufrequtils \
  irqbalance \
  unzip \
  jq \
  tmux
```

### 3.3 NUMA Verification

**Check NUMA topology:**

```bash
numactl --hardware
```

Expected output:

```
available: 2 nodes (0-1)
node 0 cpus: 0 1 2 3 4 5 6 7 8 9 10 11
node 0 size: 406000 MB
node 0 free: 400000 MB
node 1 cpus: 12 13 14 15 16 17 18 19 20 21 22 23
node 1 size: 407000 MB
node 1 free: 401000 MB
node distances:
node   0   1
  0:  10  21
  1:  21  10
```

Key things to verify:
- **2 nodes** (not 4 — if you see 4, SNC is still enabled; go back to BIOS and disable it)
- **12 CPUs per node** (not 24 — if you see 24, hyperthreading is still on)
- **~406GB per node** (roughly equal — if one node has significantly more, DIMMs are not balanced)
- Node distance of 10 (local) and 21 (remote) is normal for a 2-socket Xeon

**Check CPU topology:**

```bash
lscpu
```

Verify:
- `CPU(s): 24` (12 physical cores x 2 sockets, HT off)
- `Thread(s) per core: 1` (confirms HT is off)
- `Core(s) per socket: 12`
- `Socket(s): 2`
- `NUMA node(s): 2`

**Check DIMM details:**

```bash
sudo dmidecode -t memory | grep -E "Size|Locator|Speed|Type" | head -60
```

This shows each DIMM slot, its size, speed, and which socket/channel it is in.

### 3.4 Intel MLC (Memory Latency Checker)

Intel MLC is free but not in Ubuntu repos. Download it from Intel:

```bash
cd /tmp
wget https://downloadmirror.intel.com/793041/mlc_v3.11a.tgz
tar xzf mlc_v3.11a.tgz
sudo cp Linux/mlc /usr/local/bin/
sudo chmod +x /usr/local/bin/mlc
```

> **Note:** The download URL changes with each MLC version. If the above 404s, go to https://www.intel.com/content/www/us/en/download/736633/intel-memory-latency-checker-intel-mlc.html and get the current Linux tarball. The archive structure is typically `Linux/mlc`.

**Run a bandwidth test:**

```bash
sudo mlc --bandwidth_matrix
```

Expected output shows bandwidth in MB/s between NUMA nodes. You want to see:
- Local bandwidth (node 0 to node 0, node 1 to node 1): ~40-50 GB/s per socket with DDR4-3200 across 8 channels
- Remote bandwidth (cross-socket): lower, typically 60-70% of local

```bash
sudo mlc --latency_matrix
```

This shows latency in nanoseconds. Local should be ~80-90ns, remote ~130-150ns.

Save these results for reference:

```bash
sudo mkdir -p /data/benchmarks
sudo mlc --bandwidth_matrix > /data/benchmarks/mlc_bandwidth.txt 2>&1
sudo mlc --latency_matrix > /data/benchmarks/mlc_latency.txt 2>&1
```

### 3.5 Network Configuration — Static IP

Ubuntu 24.04 server uses Netplan. Find your current config:

```bash
ls /etc/netplan/
```

Typically there is one file like `00-installer-config.yaml` or `50-cloud-init.yaml`.

Edit it (back up first):

```bash
sudo cp /etc/netplan/00-installer-config.yaml /etc/netplan/00-installer-config.yaml.bak
sudo nano /etc/netplan/00-installer-config.yaml
```

Replace the contents with your static IP config. Example:

```yaml
network:
  version: 2
  ethernets:
    eno1:
      dhcp4: false
      addresses:
        - 192.168.1.100/24  # <-- your static IP
      routes:
        - to: default
          via: 192.168.1.1    # <-- your gateway
      nameservers:
        addresses:
          - 1.1.1.1
          - 8.8.8.8
```

Apply:

```bash
sudo netplan apply
```

> **Warning:** If you are connected via SSH on the interface you just reconfigured, you will lose your connection if the IP changes. Make sure you know the new IP, or do this from the iDRAC console.

### 3.6 Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

This prints a URL. Open it in your browser to authenticate with your Tailscale account. Once authenticated, the server gets a Tailscale IP (100.x.x.x) and is accessible from any device on your tailnet.

Verify:

```bash
tailscale status
```

You should see this machine listed as connected.

Optional: enable Tailscale SSH (so you can SSH via Tailscale identity without keys):

```bash
sudo tailscale up --ssh
```

### 3.7 Kernel Parameters

Edit the GRUB default config to add kernel parameters:

```bash
sudo nano /etc/default/grub
```

Find the line `GRUB_CMDLINE_LINUX_DEFAULT` and set it to:

```
GRUB_CMDLINE_LINUX_DEFAULT="numa_balancing=0 transparent_hugepage=always processor.max_cstate=1 intel_idle.max_cstate=0"
```

Explanation of each parameter:
- `numa_balancing=0` — Disables automatic NUMA page migration. You are manually pinning Ollama instances to NUMA nodes; you do not want the kernel moving pages between nodes behind your back. This is critical for predictable inference latency.
- `transparent_hugepage=always` — Enables transparent huge pages (2MB instead of 4KB). LLM inference allocates large contiguous memory blocks; THP reduces TLB misses significantly. Some databases (PostgreSQL, Redis) recommend disabling THP, but since those are running in Docker with relatively small memory footprints compared to Ollama, the tradeoff favors THP here.
- `processor.max_cstate=1` — Belt-and-suspenders enforcement of C-state limits at the kernel level (in addition to BIOS settings).
- `intel_idle.max_cstate=0` — Disables the `intel_idle` driver's C-state management, letting the BIOS settings be authoritative.

Apply:

```bash
sudo update-grub
```

Also set `vm.swappiness` low since you have 813GB of RAM and want to avoid swapping:

```bash
echo 'vm.swappiness=1' | sudo tee -a /etc/sysctl.d/99-inference.conf
echo 'vm.dirty_ratio=10' | sudo tee -a /etc/sysctl.d/99-inference.conf
echo 'vm.dirty_background_ratio=5' | sudo tee -a /etc/sysctl.d/99-inference.conf
echo 'kernel.numa_balancing=0' | sudo tee -a /etc/sysctl.d/99-inference.conf
sudo sysctl --system
```

Reboot to apply the GRUB changes:

```bash
sudo reboot
```

After reboot, verify:

```bash
cat /proc/cmdline
# Should contain numa_balancing=0, transparent_hugepage=always, etc.

cat /sys/kernel/mm/transparent_hugepage/enabled
# Should show: [always] madvise never

cat /proc/sys/vm/swappiness
# Should show: 1

cat /proc/sys/kernel/numa_balancing
# Should show: 0
```

### 3.8 CPU Governor Verification

With the Performance BIOS profile, the CPU governor should already be set to `performance`. Verify:

```bash
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

Should say `performance`. If it says `powersave` or `ondemand`:

```bash
for i in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance | sudo tee $i; done
```

Make it persistent:

```bash
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
sudo systemctl restart cpufrequtils
```

### 3.9 /data Directory Setup

```bash
sudo mkdir -p /data/{models,postgres,redis,embeddings,logs,benchmarks,ollama-0,ollama-1}
sudo chown -R $USER:$USER /data
```

Verify XFS is mounted correctly:

```bash
df -Th /data
```

Should show something like:

```
Filesystem     Type  Size  Used Avail Use% Mounted on
/dev/sdb1      xfs   8.7T   33M  8.7T   1% /data
```

---

## Part 4: Docker Installation

### 4.1 Install Docker Engine

Do NOT install the `docker.io` snap or the apt package from Ubuntu's default repos — it is outdated. Use Docker's official repository:

```bash
# Add Docker's official GPG key
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to the docker group (so you don't need sudo for docker commands)
sudo usermod -aG docker $USER
```

Log out and back in for the group change to take effect, then verify:

```bash
docker run hello-world
```

---

## Part 5: Ollama Dual-Instance Setup

### 5.1 Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

This installs the `ollama` binary to `/usr/local/bin/ollama` and creates a systemd service. **Disable the default service** — you are going to run two custom ones:

```bash
sudo systemctl stop ollama
sudo systemctl disable ollama
```

### 5.2 Create Ollama System User (if not already created by installer)

The Ollama install script usually creates an `ollama` user. Verify:

```bash
id ollama
```

If it does not exist:

```bash
sudo useradd -r -s /bin/false -m -d /usr/share/ollama ollama
```

Give it ownership of the data directories:

```bash
sudo chown -R ollama:ollama /data/ollama-0 /data/ollama-1
```

### 5.3 Systemd Service — Instance 0 (Socket 0, Port 11434)

Create the service file:

```bash
sudo tee /etc/systemd/system/ollama-0.service << 'UNIT'
[Unit]
Description=Ollama LLM Service — NUMA Node 0
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/numactl --cpunodebind=0 --membind=0 /usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3

# Environment
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_MODELS=/data/ollama-0/models"
Environment="OLLAMA_NUM_THREAD=12"
Environment="OLLAMA_KEEP_ALIVE=-1"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
Environment="HOME=/data/ollama-0"

# Security hardening
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
```

### 5.4 Systemd Service — Instance 1 (Socket 1, Port 11435)

```bash
sudo tee /etc/systemd/system/ollama-1.service << 'UNIT'
[Unit]
Description=Ollama LLM Service — NUMA Node 1
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/numactl --cpunodebind=1 --membind=1 /usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3

# Environment
Environment="OLLAMA_HOST=0.0.0.0:11435"
Environment="OLLAMA_MODELS=/data/ollama-1/models"
Environment="OLLAMA_NUM_THREAD=12"
Environment="OLLAMA_KEEP_ALIVE=-1"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
Environment="HOME=/data/ollama-1"

# Security hardening
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
```

### 5.5 Enable and Start Both Instances

```bash
sudo systemctl daemon-reload
sudo systemctl enable ollama-0 ollama-1
sudo systemctl start ollama-0 ollama-1
```

Verify both are running:

```bash
sudo systemctl status ollama-0 ollama-1
```

Both should show `active (running)`.

Test the endpoints:

```bash
curl http://localhost:11434/api/version
curl http://localhost:11435/api/version
```

Both should return JSON with the Ollama version.

### 5.6 Verify NUMA Pinning

While both instances are running:

```bash
# Get the PIDs
OPIT0=$(pgrep -f "ollama.*11434" | head -1)
OPIT1=$(pgrep -f "ollama.*11435" | head -1)

# Check which NUMA node each is bound to
numastat -p $OPIT0
numastat -p $OPIT1
```

Instance 0 should show nearly all memory allocated on Node 0, and Instance 1 on Node 1. If you see significant allocation on the "wrong" node, something is off with the numactl binding.

Also verify CPU affinity:

```bash
taskset -cp $OPIT0
# Should show CPUs 0-11

taskset -cp $OPIT1
# Should show CPUs 12-23
```

### 5.7 Pull a Test Model and Verify

Pull a small model on each instance to verify everything works:

```bash
# Pull on instance 0
OLLAMA_HOST=http://localhost:11434 ollama pull llama3.2:1b

# Pull on instance 1
OLLAMA_HOST=http://localhost:11435 ollama pull llama3.2:1b
```

> **Note:** Each instance has its own model directory (`/data/ollama-0/models` and `/data/ollama-1/models`). Models must be pulled separately to each instance. This uses more disk but ensures NUMA-local memory allocation when the model loads.

Run inference on each:

```bash
# Test instance 0
curl -s http://localhost:11434/api/generate -d '{"model":"llama3.2:1b","prompt":"Hello, which socket am I on?","stream":false}' | jq .response

# Test instance 1
curl -s http://localhost:11435/api/generate -d '{"model":"llama3.2:1b","prompt":"Hello, which socket am I on?","stream":false}' | jq .response
```

Both should return generated text within a few seconds.

### 5.8 Warmup Script (Preload Models After Boot)

Create a script that preloads your production models after boot so they are resident in memory and ready for instant inference:

```bash
sudo tee /usr/local/bin/ollama-warmup.sh << 'SCRIPT'
#!/bin/bash
# Warmup script: preload models into memory on both Ollama instances
# Runs after boot to ensure models are loaded and KEEP_ALIVE=-1 holds them

set -e

echo "[$(date)] Starting Ollama warmup..."

# Wait for both instances to be ready
for port in 11434 11435; do
  echo "Waiting for Ollama on port $port..."
  until curl -sf http://localhost:$port/api/version > /dev/null 2>&1; do
    sleep 2
  done
  echo "Ollama on port $port is ready."
done

# Define which models to load on which instance
# Adjust these to your actual production models
MODELS_SOCKET0=("llama3.2:1b")
MODELS_SOCKET1=("llama3.2:1b")

# Preload on Socket 0
for model in "${MODELS_SOCKET0[@]}"; do
  echo "Loading $model on Socket 0 (port 11434)..."
  curl -sf http://localhost:11434/api/generate -d "{\"model\":\"$model\",\"prompt\":\"warmup\",\"stream\":false}" > /dev/null
  echo "  $model loaded."
done

# Preload on Socket 1
for model in "${MODELS_SOCKET1[@]}"; do
  echo "Loading $model on Socket 1 (port 11435)..."
  curl -sf http://localhost:11435/api/generate -d "{\"model\":\"$model\",\"prompt\":\"warmup\",\"stream\":false}" > /dev/null
  echo "  $model loaded."
done

echo "[$(date)] Warmup complete."
SCRIPT

sudo chmod +x /usr/local/bin/ollama-warmup.sh
```

Create a systemd service for the warmup:

```bash
sudo tee /etc/systemd/system/ollama-warmup.service << 'UNIT'
[Unit]
Description=Ollama Model Warmup
After=ollama-0.service ollama-1.service
Requires=ollama-0.service ollama-1.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/ollama-warmup.sh
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable ollama-warmup
```

---

## Part 6: Data Store Setup

### 6.1 Docker Compose for PostgreSQL and Redis

Create the compose file:

```bash
mkdir -p /data/docker
```

```yaml
# /data/docker/docker-compose.yml
services:
  postgres:
    image: postgres:16
    container_name: postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: inference
      POSTGRES_PASSWORD: CHANGE_ME_TO_A_REAL_PASSWORD
      POSTGRES_DB: langgraph
    volumes:
      - /data/postgres:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"
    shm_size: '256m'
    command: >
      postgres
        -c shared_buffers=512MB
        -c work_mem=64MB
        -c maintenance_work_mem=256MB
        -c effective_cache_size=2GB
        -c max_connections=100
        -c wal_level=replica
        -c max_wal_size=2GB
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U inference -d langgraph"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis/redis-stack-server:latest
    container_name: redis
    restart: unless-stopped
    volumes:
      - /data/redis:/data
    ports:
      - "127.0.0.1:6379:6379"
    command: >
      redis-stack-server
        --maxmemory 4gb
        --maxmemory-policy allkeys-lru
        --save 60 1000
        --appendonly yes
        --bind 0.0.0.0
        --protected-mode yes
        --requirepass CHANGE_ME_TO_A_REAL_PASSWORD
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "CHANGE_ME_TO_A_REAL_PASSWORD", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```

> **Warning:** Change both `CHANGE_ME_TO_A_REAL_PASSWORD` values to actual strong passwords. Use `openssl rand -base64 24` to generate one.

> **Note on binding:** Both services bind to `127.0.0.1` only — they are not exposed to the network. Access from other machines should go through Tailscale and an SSH tunnel, or you can later change the bind address to the Tailscale IP (100.x.x.x) if needed.

> **Note on redis-stack-server:** This image includes RedisJSON and RediSearch modules built-in. No extra configuration needed — the modules are loaded automatically.

Start the containers:

```bash
cd /data/docker
docker compose up -d
```

Verify:

```bash
docker compose ps
```

Both should show `healthy` after 10-20 seconds:

```
NAME       IMAGE                              STATUS
postgres   postgres:16                        Up (healthy)
redis      redis/redis-stack-server:latest    Up (healthy)
```

Test connectivity:

```bash
# PostgreSQL
docker exec postgres psql -U inference -d langgraph -c "SELECT version();"

# Redis
docker exec redis redis-cli -a CHANGE_ME_TO_A_REAL_PASSWORD ping
# Should return: PONG

# Test RedisJSON module
docker exec redis redis-cli -a CHANGE_ME_TO_A_REAL_PASSWORD MODULE LIST
# Should list "ReJSON" and "search" among loaded modules
```

### 6.2 PostgreSQL Schema for LangGraph Checkpoints

LangGraph's checkpoint system uses a specific schema. Create it:

```bash
docker exec -i postgres psql -U inference -d langgraph << 'SQL'
-- LangGraph checkpoint tables
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);

-- Index for efficient thread lookups
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread
    ON checkpoints (thread_id, checkpoint_ns, created_at DESC);

-- Grant permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO inference;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO inference;

SELECT 'LangGraph schema created successfully' AS status;
SQL
```

### 6.3 SQLite-vec for Embeddings

SQLite-vec is a SQLite extension for vector similarity search. It is lightweight and perfect for local embeddings.

```bash
# Install Python 3 and pip (should already be present on Ubuntu 24.04)
sudo apt install -y python3-pip python3-venv

# Create a virtual environment for embedding tools
python3 -m venv /data/embeddings/venv
source /data/embeddings/venv/bin/activate

# Install sqlite-vec
pip install sqlite-vec

# Verify it works
python3 << 'PYEOF'
import sqlite3
import sqlite_vec

db = sqlite3.connect("/data/embeddings/vectors.db")
db.enable_load_extension(True)
sqlite_vec.load(db)

# Verify the extension loaded
version = db.execute("SELECT vec_version()").fetchone()[0]
print(f"sqlite-vec version: {version}")

# Create a sample table for embeddings
db.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS embeddings USING vec0(
        id TEXT PRIMARY KEY,
        embedding float[1536]
    )
""")
db.commit()
print("Embeddings table created successfully.")
db.close()
PYEOF

deactivate
```

Enable auto-start for Docker Compose on boot:

```bash
sudo tee /etc/systemd/system/docker-datastore.service << 'UNIT'
[Unit]
Description=Docker Compose Data Stores (PostgreSQL + Redis)
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/data/docker
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable docker-datastore
```

---

## Part 7: Verification Checklist

Run through this checklist after everything is set up. Every item should pass.

### 7.1 NUMA Topology

```bash
echo "=== NUMA Topology ==="
numactl --hardware | head -10
echo ""
echo "=== CPU Layout ==="
lscpu | grep -E "CPU\(s\)|Thread|Core|Socket|NUMA"
```

**Expected:**
- 2 NUMA nodes
- 12 cores per socket
- 1 thread per core
- ~406GB per node

### 7.2 Kernel Parameters

```bash
echo "=== Kernel Params ==="
echo "NUMA balancing: $(cat /proc/sys/kernel/numa_balancing)"
echo "Swappiness: $(cat /proc/sys/vm/swappiness)"
echo "THP: $(cat /sys/kernel/mm/transparent_hugepage/enabled)"
echo "CPU governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
echo ""
echo "=== Boot cmdline ==="
cat /proc/cmdline
```

**Expected:** numa_balancing=0, swappiness=1, THP=[always], governor=performance

### 7.3 Ollama Instances

```bash
echo "=== Ollama Instance 0 ==="
curl -s http://localhost:11434/api/version | jq .
echo ""
echo "=== Ollama Instance 1 ==="
curl -s http://localhost:11435/api/version | jq .
echo ""
echo "=== Service Status ==="
systemctl is-active ollama-0 ollama-1
```

**Expected:** Both return version JSON, both show `active`.

### 7.4 Test Inference on Both Sockets

```bash
echo "=== Inference on Socket 0 ==="
time curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3.2:1b","prompt":"Say hello in exactly 5 words.","stream":false}' | jq .response

echo ""
echo "=== Inference on Socket 1 ==="
time curl -s http://localhost:11435/api/generate \
  -d '{"model":"llama3.2:1b","prompt":"Say hello in exactly 5 words.","stream":false}' | jq .response
```

**Expected:** Both return text. Note the response times — they should be similar (within 10-20% of each other). If one is significantly slower, check DIMM balance.

### 7.5 Docker Containers

```bash
echo "=== Docker Containers ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Expected:**

```
NAMES      STATUS           PORTS
postgres   Up X (healthy)   127.0.0.1:5432->5432/tcp
redis      Up X (healthy)   127.0.0.1:6379->6379/tcp
```

### 7.6 PostgreSQL Schema

```bash
echo "=== PostgreSQL Tables ==="
docker exec postgres psql -U inference -d langgraph -c "\dt"
```

**Expected:** Should list `checkpoints`, `checkpoint_writes`, and `checkpoint_migrations` tables.

### 7.7 Redis Modules

```bash
echo "=== Redis Modules ==="
docker exec redis redis-cli -a CHANGE_ME_TO_A_REAL_PASSWORD MODULE LIST | head -20
```

**Expected:** Shows `ReJSON` (version 2.x) and `search` (RediSearch, version 2.x).

### 7.8 Tailscale

```bash
echo "=== Tailscale ==="
tailscale status | head -5
echo ""
echo "Tailscale IP: $(tailscale ip -4)"
```

**Expected:** Shows this machine as connected, with a 100.x.x.x IP.

### 7.9 Storage

```bash
echo "=== Storage ==="
df -Th / /boot/efi /data
echo ""
echo "=== Block Devices ==="
lsblk
```

**Expected:**
- `/` is ext4 on ~204G, on the BOSS M.2
- `/data` is xfs on ~8.7T, on the PERC H755

### 7.10 Intel MLC (Run Last — Takes a Few Minutes)

```bash
echo "=== Memory Bandwidth ==="
sudo mlc --bandwidth_matrix
```

**Expected:** Local bandwidth per node in the 40-50 GB/s range for DDR4-3200 with 8 channels populated.

---

## Common Mistakes and Troubleshooting

**"I see 4 NUMA nodes instead of 2"**
Sub-NUMA Clustering (SNC) is enabled. Reboot into BIOS (F2 during POST via iDRAC console) and disable SNC under Processor Settings. If you see `SNC` or `Sub NUMA Cluster` set to "Enabled" or "SNC-2", change to "Disabled."

**"I see 48 CPUs instead of 24"**
Hyperthreading is still on. Reboot into BIOS and set Logical Processor to "Disabled."

**"lscpu shows governor = powersave"**
The kernel's `intel_pstate` driver may be overriding BIOS settings. Fix:
```bash
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```
For permanence, use `cpufrequtils` as described in section 3.8.

**"The installer doesn't see the PERC H755 array"**
Make sure you created the virtual disk in iDRAC (section 1.6). The installer sees virtual disks, not raw physical drives. If no virtual disk is configured, there is nothing for Linux to mount.

**"Ollama is slow on one socket"**
Run `numastat -p <PID>` for the slow instance. If it shows significant "Other Node" memory allocation, the model data is being pulled from remote NUMA memory. This can happen if:
- DIMMs are unbalanced (one socket has less RAM)
- The model is too large for one socket's memory and is spilling to the other node
- NUMA balancing is on and migrated pages

**"/data is not mounted after reboot"**
Check that `/etc/fstab` has an entry for `/data`. The Ubuntu installer should have added one, but verify:
```bash
cat /etc/fstab | grep data
```
If missing, add:
```
/dev/sdb1  /data  xfs  defaults,noatime  0  2
```
Use `blkid /dev/sdb1` to get the UUID and use `UUID=xxxx` instead of `/dev/sdb1` for a more robust fstab entry.

**"Virtual media is incredibly slow during install"**
This is normal for iDRAC virtual media — it streams the ISO over the management network. For faster install, use a physical USB stick plugged into the server's front USB port. Write the ISO with:
```bash
# On your workstation:
sudo dd if=ubuntu-24.04-live-server-amd64.iso of=/dev/sdX bs=4M status=progress
```
(Replace `/dev/sdX` with your USB device. Use `lsblk` to find it. Triple-check you have the right device.)

**"iDRAC virtual console keyboard not working"**
Switch between the HTML5 console and the Java/ActiveX console (if available). Also try the iDRAC virtual console keyboard macro buttons for special keys like F2, F11, etc. Some keyboard layouts cause issues — try connecting with a US English keyboard layout in your browser.

**"BOSS M.2 shows degraded RAID"**
One of the two M.2 sticks may have failed or be unseated. Check iDRAC storage page for the BOSS controller. If one drive is missing, it needs physical reseating or replacement. The system will still boot from the surviving drive in degraded mode, but fix this ASAP to restore the mirror.

---

## Summary of Services and Ports

| Service | Port | Bound To | Notes |
|---|---|---|---|
| Ollama Instance 0 | 11434 | 0.0.0.0 | NUMA Node 0, Socket 0 |
| Ollama Instance 1 | 11435 | 0.0.0.0 | NUMA Node 1, Socket 1 |
| PostgreSQL | 5432 | 127.0.0.1 | LangGraph checkpoints |
| Redis Stack | 6379 | 127.0.0.1 | RedisJSON + RediSearch |
| SSH | 22 | 0.0.0.0 | Standard SSH |
| Tailscale | - | 100.x.x.x | VPN mesh overlay |

> **Security note:** Ollama is bound to 0.0.0.0 so it is accessible from Tailscale peers. If your server is on an untrusted network, consider binding Ollama to 127.0.0.1 and the Tailscale IP only, or use firewall rules:
> ```bash
> sudo ufw enable
> sudo ufw default deny incoming
> sudo ufw allow ssh
> sudo ufw allow in on tailscale0
> ```
> This allows all traffic from Tailscale but blocks everything else except SSH.
