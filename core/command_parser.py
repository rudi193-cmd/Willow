"""Deterministic command parser - no LLM guessing"""
import re
from typing import Optional, Dict, Any

def parse_command(user_input: str) -> Optional[Dict[str, Any]]:
    """
    Parse user input and return tool call if pattern matches.
    Returns None if should be conversational response.
    """
    text = user_input.lower().strip()
    
    # Greetings - no tools
    greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening', 'thanks', 'thank you']
    if any(g in text for g in greetings) and len(text.split()) <= 3:
        return None  # Conversational response
    
    # List files / ls
    if re.search(r'\b(list files?|ls|dir|show files?)\b', text):
        # Extract path if specified
        path_match = re.search(r'in\s+([/\w\.-]+)|at\s+([/\w\.-]+)', text)
        if path_match:
            path = path_match.group(1) or path_match.group(2)
            return {"tool": "bash_exec", "params": {"command": f"ls -la {path}"}}
        return {"tool": "bash_exec", "params": {"command": "ls -la"}}
    
    # Change directory
    if re.search(r'\b(cd|change dir|go to)\b', text):
        path_match = re.search(r'(?:cd|to)\s+([/\w\.-]+)', text)
        if path_match:
            path = path_match.group(1)
            return {"tool": "bash_exec", "params": {"command": f"cd {path} && pwd"}}
    
    # Git commands
    if text.startswith('git '):
        return {"tool": "bash_exec", "params": {"command": text}}
    
    # Read file
    if re.search(r'\b(read|show|cat|view)\b.*\b\w+\.\w+\b', text):
        # Extract filename
        file_match = re.search(r'([\w/\.-]+\.\w+)', text)
        if file_match:
            filename = file_match.group(1)
            return {"tool": "read_file", "params": {"file_path": filename}}
    
    # Write file
    if re.search(r'\b(write|create)\s+[\w/\.-]+\.\w+', text):
        # Extract filename and content
        # Pattern: "write test.txt with content X" or "create file.py"
        file_match = re.search(r'(?:write|create)\s+([\w/\.-]+\.\w+)', text)
        if file_match:
            filename = file_match.group(1)
            # Extract content after "with" or "containing"
            content_match = re.search(r'(?:with|containing|content)\s+(.+)', text, re.IGNORECASE)
            content = content_match.group(1) if content_match else ""
            return {"tool": "write_file", "params": {"file_path": filename, "content": content}}
    
    # Edit file
    if re.search(r'(edit|change|update|replace).*(file|in)', text):
        # Pattern: "edit file.py change X to Y" or "replace X with Y in file.py"
        file_match = re.search(r'([\w/\.-]+\.\w+)', text)
        if file_match:
            filename = file_match.group(1)
            # Extract old and new text
            # Pattern: "change X to Y" or "replace X with Y"
            replace_match = re.search(r'(?:change|replace)\s+"([^"]+)"\s+(?:to|with)\s+"([^"]+)"', text)
            if not replace_match:
                replace_match = re.search(r'(?:change|replace)\s+(\w+)\s+(?:to|with)\s+(\w+)', text)
            if replace_match:
                old_text = replace_match.group(1)
                new_text = replace_match.group(2)
                return {"tool": "edit_file", "params": {"file_path": filename, "old_text": old_text, "new_text": new_text}}
    
    
    # Search / grep
    if re.search(r'\b(search|grep|find)\b.*\bfor\b', text):
        # Extract search pattern
        pattern_match = re.search(r'for\s+"([^"]+)"|for\s+(\w+)', text)
        if pattern_match:
            pattern = pattern_match.group(1) or pattern_match.group(2)
            return {"tool": "grep_search", "params": {"pattern": pattern, "path": "."}}
    
    # Find files by pattern
    if re.search(r'\bfind\b.*\bfiles?\b', text) or re.search(r'\*\.\w+', text):
        # Extract glob pattern
        pattern_match = re.search(r'(\*\*?/?\*?\.\w+|\*\*?/?\w+)', text)
        if pattern_match:
            pattern = pattern_match.group(1)
            return {"tool": "glob_find", "params": {"pattern": pattern}}
    
    # List tasks
    if re.search(r'\b(list|show|view)\b.*\btasks?\b', text):
        return {"tool": "task_list", "params": {}}
    
    # Web search
    if re.search(r'\b(search|google|look up)\b.*\b(internet|web|online)\b', text):
        # Extract query (remove search-related words)
        query = re.sub(r'\b(search|google|look up|on|the|internet|web|online|for)\b', '', text).strip()
        return {"tool": "web_search", "params": {"query": query, "max_results": 5}}
    
    # What directories / pwd
    if re.search(r'\b(what|which|show)\b.*(director|folder|path)', text):
        return {"tool": "bash_exec", "params": {"command": "pwd && ls -d */"}}
    
    # Generic bash command (starts with common commands)
    bash_commands = ['echo', 'cat', 'grep', 'find', 'pwd', 'whoami', 'date', 'uname']
    if any(text.startswith(cmd) for cmd in bash_commands):
        return {"tool": "bash_exec", "params": {"command": text}}

    # COMPLEX ANALYSIS (Free Fleet)
    # Analyze file/code
    if re.search(r'\b(analyze|review|check)\b.*\b\w+\.\w+\b', text):
        file_match = re.search(r'([\w/\\.-]+\.\w+)', text)
        if file_match:
            filename = file_match.group(1)
            return {"analysis": "analyze", "target": filename}

    # Explain concept/code
    if re.search(r'\b(explain|describe|what is|how does)\b', text):
        # Extract topic (everything after the command word)
        topic_match = re.search(r'(?:explain|describe|what is|how does)\s+(.+)', text, re.IGNORECASE)
        if topic_match:
            topic = topic_match.group(1).strip()
            return {"analysis": "explain", "topic": topic}

    # Summarize file/content
    if re.search(r'\b(summarize|summary of)\b', text):
        file_match = re.search(r'([\w/\\.-]+\.\w+)', text)
        if file_match:
            filename = file_match.group(1)
            return {"analysis": "summarize", "target": filename}
        else:
            # Summarize general topic
            topic_match = re.search(r'(?:summarize|summary of)\s+(.+)', text, re.IGNORECASE)
            if topic_match:
                topic = topic_match.group(1).strip()
                return {"analysis": "summarize", "topic": topic}

    # No pattern matched - conversational response
    return None
