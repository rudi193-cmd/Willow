"""Cross-platform shell adapter for bash_exec"""
import subprocess
import platform
import shutil
from pathlib import Path

def find_git_bash():
    """Find Git Bash on Windows."""
    common_paths = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        Path.home() / "AppData/Local/Programs/Git/bin/bash.exe"
    ]
    
    for path in common_paths:
        if Path(path).exists():
            return str(path)
    
    # Try PATH
    git_bash = shutil.which("bash")
    # Exclude WSL relay (System32ash.exe routes into docker-desktop which has no /bin/bash)
    if git_bash and "System32" in git_bash:
        return None
    return git_bash

def execute_command(command: str, timeout: int = 60):
    """
    Execute shell command cross-platform.
    
    Args:
        command: Shell command to execute
        timeout: Timeout in seconds
        
    Returns:
        dict with stdout, stderr, returncode
    """
    is_windows = platform.system() == "Windows"
    
    if is_windows:
        # Try Git Bash first for better compatibility
        git_bash = find_git_bash()
        
        if git_bash:
            # Use Git Bash for Unix-style commands
            try:
                result = subprocess.run(
                    [git_bash, "-c", command],
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            except Exception:
                pass  # Fallback to cmd.exe
        
        # Fallback: Use cmd.exe with command translation
        translated = translate_for_windows(command)
        result = subprocess.run(
            translated,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
    else:
        # Linux/Mac: use bash directly
        result = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout
        )
    
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }

def translate_for_windows(command: str) -> str:
    """Translate common Unix commands to Windows equivalents."""
    # Don't translate if Git Bash is being used
    return command
    
    # Simple word-based translation
    for unix_cmd, win_cmd in translations.items():
        if command.strip().startswith(unix_cmd):
            return command.replace(unix_cmd, win_cmd, 1)
    
    return command
