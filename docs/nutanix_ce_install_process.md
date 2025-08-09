# Nutanix CE Installation Process

The execution flow from `ce_installer` to the main `phoenix` installer  is a multi-step process through several shell scripts and Python programs.

## Execution Flow Diagram

```bash
ce_installer (symlink) 
    ↓
livecd.sh (detects CE mode)
    ↓  
do_ce_installer.sh (sets CE environment)
    ↓
do_installer.sh (prepares and launches)
    ↓
phoenix (Python installer)
```

## Step-by-Step Breakdown

### 1. **ce_installer → livecd.sh**

`ce_installer` is actually a **symbolic link** to `livecd.sh`:

```bash
# In the initrd/squashfs
ce_installer -> livecd.sh
```

When `init=/ce_installer` is passed as a kernel parameter, it executes `livecd.sh`.

### 2. **livecd.sh Logic Detection**

In `livecd.sh`, this code detects Community Edition mode:

```bash
ce=0
if [ "${0##*/}" == "ce_installer" ]; then
  ce=1
fi
```

Since the script was called as `ce_installer`, `ce=1` is set, enabling CE-specific behavior.

### 3. **livecd.sh → do_ce_installer.sh**

At the end of `livecd.sh`:

```bash
script=${0##*/}  # script = "ce_installer"

if [ -e "$HOME/do_${script}.sh" ]; then
  . "$HOME/do_${script}.sh"    # Sources do_ce_installer.sh
else
  echo "ERROR: $HOME/do_${script}.sh not found."
  drop_to_shell
fi
```

This **sources** (executes) `do_ce_installer.sh`.

### 4. **do_ce_installer.sh Environment Setup**

`do_ce_installer.sh` sets up Community Edition environment:

```bash
export COMMUNITY_EDITION=1

# Read network info if available
CE_NET_INFO=""
if [ -f /mnt/stage/root/.host_net_info ]; then
  CE_NET_INFO=`cat /mnt/stage/root/.host_net_info`
fi
if [ -f /mnt/stage/root/.cvm_net_info ]; then
  CE_NET_INFO=$CE_NET_INFO" "
  CE_NET_INFO=$CE_NET_INFO`cat /mnt/stage/root/.cvm_net_info`
fi
if [ ! -z "$CE_NET_INFO" ]; then
  export CE_INSTALLED=`echo $CE_NET_INFO`
fi

# Remove any previous install markers
rm -f /mnt/stage/root/.ce_install_success

# Call the main installer
sh /root/do_installer.sh
```

### 5. **do_installer.sh → phoenix**

`do_installer.sh` prepares the Python environment and launches the main installer:

```bash
# Install foundation layout Python package
/usr/bin/easy_install -Z --no-find-links --no-deps /root/phoenix/egg_basket/foundation_layout*.egg 1>/dev/null

# Change to phoenix directory
cd /phoenix

# Apply any patches/updates
./patch_phoenix.py --url $UPDATES_CONFIG_URL

# Install additional components
/phoenix/install_components.py

# Determine the init script name
script=$(grep "init=" /proc/cmdline | sed "s/.*init="'\(\S*\).*/\1/')

# Launch phoenix in screen session for CE
if [[ -e '/etc/redhat-release' && ($(basename $script) = "installer" || $(basename $script) = "ce_installer") ]]; then
 screen -dmSL centos_phoenix ./phoenix $@
else
 ./phoenix $@
fi
```

### 6. **phoenix Python Application**

Finally, `phoenix` (the Python script) runs with the `COMMUNITY_EDITION=1` environment variable set.

In `phoenix` (Python), this environment variable triggers CE-specific behavior:

```python
def main():
  cmdline_args = sysUtil.parse_cmd_line()
  unattended = False

  # ... (Arizona configuration handling)

  elif 'COMMUNITY_EDITION' in os.environ:
    params = gui.get_params(gui.CEGui)  # Launch CE GUI instead of full GUI
  
  # ... (rest of installation logic)
```

## Key Points in the Chain

### **Environment Variables Set:**
- `COMMUNITY_EDITION=1` - Triggers CE mode in Python
- `CE_INSTALLED` - Contains previous network info if available

### **Working Directory Changes:**
- Starts in `/` (root)
- Changes to `/phoenix` before launching Python installer

### **Screen Session:**
- CE installer runs in a `screen` session named `centos_phoenix`
- Allows reconnection if SSH session drops

### **Error Handling:**
- Each step has error checking
- Falls back to shell on failure (`drop_to_shell`)

## Why This Multi-Step Process?

1. **Modularity**: Each script handles a specific phase
2. **Environment Setup**: Gradual environment preparation
3. **Error Recovery**: Multiple checkpoints for debugging
4. **Flexibility**: Same framework supports different installer modes
5. **Legacy Support**: Maintains compatibility with older deployment methods

## Summary

The path is: **Kernel** → **livecd.sh** (with CE detection) → **do_ce_installer.sh** (CE environment) → **do_installer.sh** (Python prep) → **phoenix** (main installer)

Each step builds upon the previous one, ultimately launching the Python-based Nutanix installer with Community Edition settings enabled.