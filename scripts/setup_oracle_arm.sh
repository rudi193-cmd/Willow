#!/bin/bash
# setup_oracle_arm.sh - Run on OCI ARM instance after provisioning
# Sets up Ollama, configures it to listen on 0.0.0.0, and readies it for Sean model

set -e
echo "[+] Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo "[+] Configuring Ollama to listen on all interfaces..."
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_MODELS=/models"
EOF

echo "[+] Creating models directory..."
mkdir -p /models
chmod 777 /models

echo "[+] Reloading and starting Ollama..."
systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama
sleep 3

echo "[+] Ollama status:"
systemctl is-active ollama

echo "[+] Pulling base model (llama3.2 for verify)..."
ollama pull llama3.2:latest

echo "[+] Setup complete. Ready for sean model upload."
echo "    Run: python provision_oracle.py --ip $(curl -s ifconfig.me) --gguf /path/to/sean.f16.gguf"
