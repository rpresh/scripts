#!/bin/bash

# Define key names and paths
# It is best to keep these in a secure, persistent directory
KEY_DIR="$HOME/.vmware-keys"
PRIV_KEY="$KEY_DIR/MOK.priv"
DER_KEY="$KEY_DIR/MOK.der"
KERNEL_VERSION=$(uname -r)

# Create directory if it doesn't exist
mkdir -p "$KEY_DIR"

# 1. Generate keys if they don't exist
if [[ ! -f "$PRIV_KEY" || ! -f "$DER_KEY" ]]; then
    echo "[+] Generating new MOK keys in $KEY_DIR..."
    openssl req -new -x509 -newkey rsa:2048 -keyout "$PRIV_KEY" \
        -outform DER -out "$DER_KEY" -nodes -days 36500 \
        -subj "/CN=VMware-Module-Signer/"
    
    echo "[!] New key generated. You MUST run 'sudo mokutil --import $DER_KEY' and reboot to enroll it."
else
    echo "[+] Using existing MOK keys."
fi

# 2. Find the sign-file script (path can vary slightly by distro)
SIGN_SCRIPT="/usr/src/linux-headers-$KERNEL_VERSION/scripts/sign-file"

if [[ ! -f "$SIGN_SCRIPT" ]]; then
    echo "[-] Error: Sign-file script not found. Do you have linux-headers installed?"
    exit 1
fi

# 3. Sign the modules
echo "[+] Signing vmmon for kernel $KERNEL_VERSION..."
sudo "$SIGN_SCRIPT" sha256 "$PRIV_KEY" "$DER_KEY" $(modinfo -n vmmon)

echo "[+] Signing vmnet for kernel $KERNEL_VERSION..."
sudo "$SIGN_SCRIPT" sha256 "$PRIV_KEY" "$DER_KEY" $(modinfo -n vmnet)

# 4. Attempt to load the modules
echo "[+] Attempting to load modules..."
sudo modprobe vmmon && sudo modprobe vmnet

if [ $? -eq 0 ]; then
    echo "[SUCCESS] VMware modules loaded successfully."
else
    echo "[FAILURE] Modules failed to load. If this is a new key, remember to Enroll MOK on reboot."
fi
