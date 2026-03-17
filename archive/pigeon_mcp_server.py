#!/usr/bin/env python3
"""
Pigeon MCP Server
Exposes pigeon bus messaging to Claude instances (mobile/desktop/web) via MCP
"""

import os
import requests
from typing import Optional
from fastmcp import FastMCP

# Configuration
PIGEON_API_URL = os.getenv("PIGEON_API_URL", "http://localhost:8420")
AUTH_USERNAME = os.getenv("PIGEON_USERNAME", "Sweet-Pea-Rudi19")
DEFAULT_APP_ID = os.getenv("DEFAULT_APP_ID", "claude-desktop")

# Initialize MCP server
mcp = FastMCP("Pigeon Messaging")


@mcp.tool()
def send_message(
    to: str,
    subject: str,
    body: str,
    from_app: Optional[str] = None,
    thread_id: Optional[str] = None
) -> dict:
    """
    Send a message via the pigeon bus to another app/agent.
    
    Args:
        to: Recipient app_id (e.g., "ganesha-cli", "shiva", "oakenscroll")
        subject: Message subject line
        body: Message content
        from_app: Sender app_id (defaults to oakenscroll)
        thread_id: Optional thread ID for replies
    
    Returns:
        Response from pigeon API indicating success/failure
    """
    sender = from_app or DEFAULT_APP_ID
    
    payload = {
        "topic": "send",
        "app_id": sender,
        "username": AUTH_USERNAME,
        "payload": {
            "to": to,
            "subject": subject,
            "body": body,
        }
    }
    
    if thread_id:
        payload["payload"]["thread_id"] = thread_id
    
    try:
        response = requests.post(
            f"{PIGEON_API_URL}/api/pigeon/drop",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return {
            "status": "success",
            "message": f"Message sent from {sender} to {to}",
            "response": response.json() if response.text else None
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": f"Failed to send message: {str(e)}"
        }


@mcp.tool()
def check_inbox(app_id: Optional[str] = None) -> dict:
    """
    Check inbox for messages sent to this app.
    
    Args:
        app_id: App to check inbox for (defaults to oakenscroll)
    
    Returns:
        List of unread messages from pigeon inbox
    """
    target_app = app_id or DEFAULT_APP_ID
    
    try:
        response = requests.get(
            f"{PIGEON_API_URL}/api/pigeon/inbox",
            params={"app_id": target_app},
            timeout=10
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Extract message count and unread status
        messages = data.get("messages", [])
        
        return {
            "status": "success",
            "app_id": target_app,
            "unread_count": len(messages),
            "messages": messages
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": f"Failed to check inbox: {str(e)}"
        }


@mcp.tool()
def mark_message_read(message_id: str, app_id: Optional[str] = None) -> dict:
    """
    Mark a message as read.
    
    Args:
        message_id: ID of the message to mark as read
        app_id: App that owns the message (defaults to oakenscroll)
    
    Returns:
        Status of mark-read operation
    """
    target_app = app_id or DEFAULT_APP_ID
    
    try:
        response = requests.post(
            f"{PIGEON_API_URL}/api/pigeon/inbox/{message_id}/read",
            params={"app_id": target_app},
            timeout=10
        )
        response.raise_for_status()
        
        return {
            "status": "success",
            "message": f"Message {message_id} marked as read"
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": f"Failed to mark message as read: {str(e)}"
        }


@mcp.tool()
def list_apps() -> dict:
    """
    List all registered apps in the pigeon system.
    
    Returns:
        List of available apps that can send/receive messages
    """
    try:
        response = requests.get(
            f"{PIGEON_API_URL}/api/apps",
            timeout=10
        )
        response.raise_for_status()
        
        data = response.json()
        
        return {
            "status": "success",
            "apps": data.get("apps", []),
            "count": len(data.get("apps", []))
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": f"Failed to list apps: {str(e)}"
        }


if __name__ == "__main__":
    # Run the MCP server
    # Default to HTTP transport for remote access
    mcp.run(transport="sse")
