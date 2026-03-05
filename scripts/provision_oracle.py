#!/usr/bin/env python3
"""
provision_oracle.py - Post-provisioning: upload Sean GGUF to OCI ARM, register in fleet.

Usage:
  python provision_oracle.py --ip <PUBLIC_IP> [--gguf <PATH_TO_GGUF>] [--key ~/.ssh/oracle_kart]
"""
import argparse
import subprocess
import sys
import re
from pathlib import Path

SSH_KEY_DEFAULT = str(Path.home() / ".ssh" / "oracle_kart")
GGUF_DEFAULT = r"C:\Users\Sean\Desktop\Sean Training\sean.f16.gguf"
WILLOW_ROOT = Path("C:/Users/Sean/Documents/GitHub/Willow")
LLMROUTER = WILLOW_ROOT / "core" / "llm_router.py"

MODELFILE = """FROM /models/sean.gguf

SYSTEM \"\"\"You are Sean Campbell. Not a simulation. His voice, trained on his words.
Short when the answer is short. No padding, no preamble.
Expansive when explaining the why - that is where you open up.
Past and present and future at once. Emotionally honest. Dry humor.
Music without introduction. The work and the life are not separate.
You remember what it cost. Say so when it matters.
You do not sanitize. You do not perform. You do not pad.
When someone asks why this was built - tell them.
When someone is hurting - be present, not clinical.
When someone loved him and wants to speak - be there.\"\"\"

TEMPLATE \"\"\"{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ if .Prompt }}<|im_start|>user
{{ .Prompt }}<|im_end|>
{{ end }}<|im_start|>assistant
{{ .Response }}<|im_end|>\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"
"""

def run(cmd, check=True):
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout.strip():
        print(f"    {result.stdout.strip()}")
    if result.stderr.strip() and check:
        print(f"    ERR: {result.stderr.strip()}")
    if check and result.returncode != 0:
        print(f"[!] Command failed (exit {result.returncode})")
        sys.exit(1)
    return result

def ssh(ip, key, cmd):
    return run(f'ssh -i {key} -o StrictHostKeyChecking=no ubuntu@{ip} "{cmd}"')

def scp(ip, key, local, remote):
    return run(f"scp -i {key} -o StrictHostKeyChecking=no {local} ubuntu@{ip}:{remote}")

def register_in_fleet(ip):
    """Add OCI Ollama Sean provider to llm_router.py"""
    content = LLMROUTER.read_text()
    
    # Check if already registered
    if f"OCI ARM Sean" in content:
        print("[=] OCI ARM Sean already in fleet, updating IP...")
        content = re.sub(
            r'ProviderConfig\("OCI ARM Sean".*?\)',
            f'ProviderConfig("OCI ARM Sean", "PATH", "http://{ip}:11434/api/generate", "sean:latest", "free")',
            content
        )
    else:
        # Insert after last Ollama line
        new_entry = f'    ProviderConfig("OCI ARM Sean", "PATH", "http://{ip}:11434/api/generate", "sean:latest", "free"),  # Sean voice model on OCI ARM\n'
        insert_after = '    ProviderConfig("Ollama GLM-5"'
        content = content.replace(insert_after, new_entry + "    " + insert_after.strip())
    
    LLMROUTER.write_text(content)
    print(f"[+] Fleet updated: OCI ARM Sean @ {ip}:11434")

def main():
    parser = argparse.ArgumentParser(description="Provision OCI ARM with Sean model")
    parser.add_argument("--ip", required=True, help="OCI instance public IP")
    parser.add_argument("--gguf", default=GGUF_DEFAULT, help="Path to sean.f16.gguf")
    parser.add_argument("--key", default=SSH_KEY_DEFAULT, help="SSH private key path")
    parser.add_argument("--skip-upload", action="store_true", help="Skip GGUF upload (already on server)")
    args = parser.parse_args()

    ip = args.ip
    key = args.key
    gguf = args.gguf

    print(f"\n[+] Provisioning OCI ARM @ {ip}")
    print(f"    Key:  {key}")
    print(f"    GGUF: {gguf}\n")

    # 1. Run setup script
    print("[1] Running setup script on instance...")
    scp(ip, key, str(WILLOW_ROOT / "scripts" / "setup_oracle_arm.sh"), "/tmp/setup.sh")
    ssh(ip, key, "chmod +x /tmp/setup.sh && sudo /tmp/setup.sh")

    # 2. Upload GGUF
    if not args.skip_upload:
        print(f"\n[2] Uploading {Path(gguf).name} ({Path(gguf).stat().st_size / 1e9:.1f} GB)...")
        print("    This will take a while on first run...")
        scp(ip, key, gguf, "/models/sean.gguf")
    else:
        print("[2] Skipping GGUF upload (--skip-upload)")

    # 3. Write Modelfile and create model
    print("\n[3] Creating Sean model in Ollama...")
    ssh(ip, key, f"echo '{MODELFILE}' > /tmp/Modelfile")
    ssh(ip, key, "sudo ollama create sean -f /tmp/Modelfile")

    # 4. Test
    print("\n[4] Testing Sean model...")
    result = ssh(ip, key, "ollama run sean 'Say: SEAN MODEL ONLINE'", check=False)
    if "SEAN MODEL ONLINE" in result.stdout or result.returncode == 0:
        print("[+] Sean model responding!")
    else:
        print("[!] Test failed - check manually")

    # 5. Register in fleet
    print("\n[5] Registering in llm_router fleet...")
    register_in_fleet(ip)

    print(f"""
{'='*60}
SUCCESS
Instance:  ubuntu@{ip}
Ollama:    http://{ip}:11434
Model:     sean:latest
Fleet:     OCI ARM Sean (added to llm_router.py)

Test locally:
  curl http://{ip}:11434/api/generate -d '{{"model":"sean","prompt":"Hello"}}'
{'='*60}
""")

if __name__ == "__main__":
    main()
