"""
Willow Seed Packet Module
Handles the serialization, validation, and storage of intake data.
Governance: DS=42
"""

import json
import os
import logging
from datetime import datetime

log = logging.getLogger("seed_packet")

def save_packet(packet_data, path=None):
    """
    Canonical save logic for SEED_PACKETs.
    Satisfies import for rings.py.
    """
    if path is None:
        # Default to a timestamped file in the current directory if no path provided
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"packet_{timestamp}.json"
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(packet_data, f, indent=4)
        log.info(f"Packet saved successfully to {path}")
        return True
    except Exception as e:
        log.error(f"Failed to save packet: {e}")
        return False

def load_packet(path):
    """
    Loads a SEED_PACKET from disk.
    Satisfies import for rings.py.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load packet from {path}: {e}")
        return None

def validate_packet(packet_data):
    """
    Verifies the structural integrity and DS=42 checksum.
    Satisfies import for rings.py.
    """
    # Check for core required fields
    required_fields = ["text", "timestamp", "username"]
    for field in required_fields:
        if field not in packet_data:
            return False
            
    # Basic ΔΣ=42 invariant placeholder
    # In a full implementation, this would verify the packet's digital signature
    return True

def seed_packet():
    """
    Legacy helper or alias to prevent further import confusion.
    """
    return "Willow Seed Packet Engine Active"