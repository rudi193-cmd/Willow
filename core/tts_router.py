"""
TTS Router — Text-to-speech with local and cloud providers.

Routes TTS requests through tiers: local → free cloud → paid
Follows llm_router.py pattern with provider health tracking.
"""

import os
import logging
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path
import requests

# Import health tracking
try:
    from . import provider_health
except ImportError:
    import provider_health

log = logging.getLogger("tts_router")

@dataclass
class TTSProvider:
    name: str
    tier: str  # "local", "free", "paid"
    env_key: Optional[str] = None

PROVIDERS = [
    # Local (always free)
    TTSProvider("Piper", "local"),  # Binary-based, fast
    TTSProvider("eSpeak", "local"),  # Fallback, built-in on most systems

    # Cloud free tier
    TTSProvider("ElevenLabs", "free", "ELEVENLABS_API_KEY"),

    # Could add later:
    # TTSProvider("Azure TTS", "free", "AZURE_TTS_KEY"),
    # TTSProvider("Google Cloud TTS", "free", "GOOGLE_CLOUD_TTS_KEY"),
]

_round_robin_index = {"local": 0, "free": 0, "paid": 0}


def get_available_providers() -> Dict[str, List[TTSProvider]]:
    """Check available TTS providers."""
    available = {"local": [], "free": [], "paid": []}

    for p in PROVIDERS:
        if p.tier == "local":
            # Check if binary exists
            if p.name == "Piper":
                piper_exe = Path(__file__).parent.parent / "piper.exe"
                if piper_exe.exists():
                    available[p.tier].append(p)
            elif p.name == "eSpeak":
                # Check if eSpeak is in PATH
                try:
                    subprocess.run(["espeak", "--version"],
                                 capture_output=True, timeout=2)
                    available[p.tier].append(p)
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass
        else:
            # Cloud providers: check for API key
            if p.env_key and os.environ.get(p.env_key):
                available[p.tier].append(p)

    return available


def speak(text: str, voice: str = "default",
          preferred_tier: str = "local",
          output_format: str = "wav") -> Optional[bytes]:
    """
    Convert text to speech audio.

    Args:
        text: Text to speak
        voice: Voice ID (provider-specific)
        preferred_tier: "local", "free", or "paid"
        output_format: Audio format ("wav", "mp3")

    Returns:
        Audio bytes or None if all providers fail
    """
    available = get_available_providers()

    # Build priority list
    priority = []
    if preferred_tier in available:
        priority.extend(available[preferred_tier])

    # Fallback cascade
    if preferred_tier != "local": priority.extend(available["local"])
    if preferred_tier != "free": priority.extend(available["free"])
    if preferred_tier != "paid": priority.extend(available["paid"])

    if not priority:
        log.warning("No TTS providers available")
        return None

    # Filter healthy providers
    provider_names = [p.name for p in priority]
    healthy_names = provider_health.get_healthy_providers(provider_names)
    healthy_providers = [p for p in priority if p.name in healthy_names]

    if not healthy_providers:
        log.warning("All TTS providers blacklisted")
        return None

    # Try providers in order
    for provider in healthy_providers:
        try:
            if provider.name == "Piper":
                audio = _speak_piper(text, voice)
            elif provider.name == "eSpeak":
                audio = _speak_espeak(text)
            elif provider.name == "ElevenLabs":
                audio = _speak_elevenlabs(text, voice)
            else:
                log.warning(f"Unknown provider: {provider.name}")
                continue

            if audio:
                provider_health.record_success(provider.name, 0)
                return audio

        except Exception as e:
            provider_health.record_failure(provider.name,
                                         type(e).__name__, str(e))
            log.warning(f"Provider {provider.name} failed: {e}")
            continue

    return None


def _speak_piper(text: str, voice: str = "en_US-lessac-medium") -> bytes:
    """Use Piper TTS (local binary)."""
    piper_exe = Path(__file__).parent.parent / "piper.exe"
    model_dir = Path.home() / ".willow" / "tts" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    # Model file: voice.onnx
    model_path = model_dir / f"{voice}.onnx"

    if not model_path.exists():
        raise FileNotFoundError(f"Piper model not found: {model_path}")

    # Run: echo "text" | piper --model voice.onnx --output_raw
    proc = subprocess.run(
        [str(piper_exe), "--model", str(model_path), "--output_raw"],
        input=text.encode("utf-8"),
        capture_output=True,
        timeout=30
    )

    if proc.returncode != 0:
        raise RuntimeError(f"Piper failed: {proc.stderr.decode()}")

    return proc.stdout


def _speak_espeak(text: str) -> bytes:
    """Use eSpeak TTS (fallback, lower quality)."""
    proc = subprocess.run(
        ["espeak", "--stdout", text],
        capture_output=True,
        timeout=30
    )

    if proc.returncode != 0:
        raise RuntimeError(f"eSpeak failed: {proc.stderr.decode()}")

    return proc.stdout


def _speak_elevenlabs(text: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> bytes:
    """Use ElevenLabs API (cloud, free tier 10K chars/month)."""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY not set")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }

    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)

    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs API error {resp.status_code}: {resp.text}")

    return resp.content


def get_voices(provider: str) -> List[str]:
    """Get available voices for a provider."""
    if provider == "Piper":
        # List downloaded models
        model_dir = Path.home() / ".willow" / "tts" / "models"
        if model_dir.exists():
            return [f.stem for f in model_dir.glob("*.onnx")]
        return []

    elif provider == "eSpeak":
        return ["default"]

    elif provider == "ElevenLabs":
        # Popular voices (could fetch from API)
        return [
            "21m00Tcm4TlvDq8ikWAM",  # Rachel
            "AZnzlk1XvdvUeBnXmlld",  # Domi
            "EXAVITQu4vr4xnSDxMaL",  # Bella
        ]

    return []


if __name__ == "__main__":
    # Test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python tts_router.py <text>")
        sys.exit(1)

    text = " ".join(sys.argv[1:])
    print(f"Speaking: {text}")

    audio = speak(text)
    if audio:
        # Save to file
        output = Path("output.wav")
        output.write_bytes(audio)
        print(f"Saved to: {output}")
    else:
        print("ERROR: No providers available")
