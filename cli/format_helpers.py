# Enhanced with terminal UI
"""Helper functions for formatting tool output - Claude Code style"""

import json
from cli.terminal_ui import *

def format_tool_output(tool_name, result_data, max_chars=2000):
    """Format tool output with colors and structure like Claude Code."""
    
    # Special handling for web_search - show clean list, not JSON
    if tool_name == "web_search" and isinstance(result_data, dict):
        success = result_data.get('success', True)
        if not success:
            return error_msg(f"Search failed: {result_data.get('error', 'Unknown error')}")
        
        result_obj = result_data.get('result', {})
        results = result_obj.get('results', [])
        
        if not results:
            return colored("No results found", Colors.DIM)
        
        # Show clean formatted results (hidden from user - LLM will summarize)
        return ""  # Don't show tool output, let LLM summarize naturally
    

    # Special handling for bash_exec - show clean output, not JSON
    if tool_name == "bash_exec" and isinstance(result_data, dict):
        success = result_data.get('success', True)
        if not success:
            return error_msg(f"Command failed: {result_data.get('error', 'Unknown error')}")
        
        result_obj = result_data.get('result', {})
        stdout = result_obj.get('stdout', '').strip()
        stderr = result_obj.get('stderr', '').strip()
        
        if stderr:
            return colored(stderr, Colors.RED)
        if stdout:
            return stdout
        return colored("(command executed, no output)", Colors.DIM)

    # Regular tool output formatting
    lines = []
    lines.append(tool_header(tool_name))
    
    # Handle error case
    if isinstance(result_data, dict):
        success = result_data.get('success', True)
        if not success:
            error = result_data.get('error', 'Unknown error')
            lines.append(error_msg(f"Error: {error}"))
            return "\n".join(lines)
        
        # Extract output
        output = None
        if 'result' in result_data:
            result_obj = result_data['result']
            if isinstance(result_obj, dict) and 'content' in result_obj:
                output = result_obj['content']
            else:
                output = result_obj
        
        if output is None:
            output = result_data.get('output') or result_data.get('data')
        
        if output is None or output == "":
            lines.append(colored("(no output)", Colors.DIM))
            return "\n".join(lines)
    else:
        output = result_data
    
    # Format based on type
    if isinstance(output, dict):
        formatted = json.dumps(output, indent=2)
        lines.append(code_block(formatted, "json"))
    elif isinstance(output, list):
        formatted = json.dumps(output, indent=2)
        lines.append(code_block(formatted, "json"))
    else:
        formatted = str(output)
        # Detect if it's code
        if '\n' in formatted and ('def ' in formatted or 'class ' in formatted or 'import ' in formatted):
            lines.append(code_block(formatted, "python"))
        else:
            lines.append(formatted)
    
    # Truncate if needed
    full_output = "\n".join(lines)
    if len(full_output) > max_chars:
        truncated = full_output[:max_chars]
        remaining = len(full_output) - max_chars
        lines = truncated.split('\n')
        lines.append(colored(f"\n... ({remaining} more characters)", Colors.DIM))
    
    return "\n".join(lines) if isinstance(lines, list) else full_output


def format_file_content(content, file_path, max_lines=50):
    """Format file content with line numbers and syntax highlighting."""
    lines = content.split('\n')
    
    output = [section_header(f"📄 {file_path}")]
    
    # Detect language
    language = ""
    if file_path.endswith('.py'):
        language = "python"
    elif file_path.endswith(('.json', '.jsonl')):
        language = "json"
    
    # Show lines with syntax highlighting
    preview = '\n'.join(lines[:max_lines])
    output.append(code_block(preview, language))
    
    # Show truncation notice
    if len(lines) > max_lines:
        remaining = len(lines) - max_lines
        output.append(colored(f"\n... ({remaining} more lines)", Colors.DIM))
    
    return '\n'.join(output)


def format_list_output(items, max_items=20):
    """Format list as bulleted output."""
    if not items:
        return colored("(empty list)", Colors.DIM)
    
    output = []
    for i, item in enumerate(items[:max_items], 1):
        bullet = colored("•", Colors.CYAN)
        output.append(f"  {bullet} {item}")
    
    if len(items) > max_items:
        remaining = len(items) - max_items
        output.append(colored(f"\n... ({remaining} more items)", Colors.DIM))
    
    return '\n'.join(output)
