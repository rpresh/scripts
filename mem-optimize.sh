#!/bin/bash
# Memory optimizations for NerdZero (CardputerZero, camera kept enabled).
# Run: sudo bash ~/mem-optimize.sh   then: sudo reboot
# Safe to re-run (idempotent).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
TS=$(date +%Y%m%d-%H%M%S)
CFG=/boot/firmware/config.txt

# Backup
cp -a "$CFG" "$CFG.bak-$TS"
cp -a /etc/hosts "/etc/hosts.bak-$TS"
echo "Backups: $CFG.bak-$TS /etc/hosts.bak-$TS"

# Fix 'sudo: unable to resolve host'
HN=$(cat /etc/hostname)
grep -qw "$HN" /etc/hosts || echo "127.0.1.1	$HN" >> /etc/hosts

# 1. GPU memory -> 76 MB (enough for imx219 camera + ISP). imx219 overlay and cma-64 left as-is.
sed -i 's/^gpu_mem=.*/gpu_mem=76/' "$CFG"
grep -q '^gpu_mem=' "$CFG" || sed -i '1i gpu_mem=76' "$CFG"

# 2. Retire the first-boot user setup BEFORE switching to console boot.
#    In console (CLI) mode userconfig.service grabs the active VT and reads the
#    device keyboard; stray keystrokes can rename the 'pi' account.
systemctl disable --now userconfig.service 2>/dev/null || true
systemctl mask userconfig.service
systemctl reset-failed userconfig.service 2>/dev/null || true
if [ -f /etc/ssh/sshd_config.d/rename_user.conf ]; then
  mv /etc/ssh/sshd_config.d/rename_user.conf "/root/rename_user.conf.bak-$TS"   # stale "SSH may not work..." banner
  systemctl reload ssh || true
fi

# 3. Boot to console; start pi's user services (APPLaunch, pipewire) at boot via linger
loginctl enable-linger pi
systemctl set-default multi-user.target

# 4. Disable unneeded services (bluetooth, avahi, wayvnc left enabled)
for u in rpcbind.service rpcbind.socket nfs-blkmap.service nfs-client.target \
         cups.service cups.socket cups.path; do
  systemctl disable --now "$u" 2>/dev/null || true
done
touch /etc/cloud/cloud-init.disabled   # stops cloud-init running at boot (re-enable: delete this file)

# 5. Swap tuning for zram
echo "vm.swappiness = 100" > /etc/sysctl.d/99-zram.conf
sysctl -q -p /etc/sysctl.d/99-zram.conf

echo; echo "--- result ---"
grep -nE '^gpu_mem|imx219|cma' "$CFG"
systemctl get-default
loginctl show-user pi -p Linger
systemctl is-enabled userconfig.service || true
sysctl vm.swappiness
echo "Done. Reboot to apply: sudo reboot"
echo "Revert: cp $CFG.bak-$TS $CFG; systemctl set-default graphical.target; rm /etc/cloud/cloud-init.disabled /etc/sysctl.d/99-zram.conf"
echo "        (userconfig stays masked; unmask with: systemctl unmask userconfig.service)"
