"""Terminal UI helpers for beautiful output like Claude Code"""
import sys
import re

# ANSI color codes
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Text colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bright colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

def supports_color():
    """Check if terminal supports colors."""
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

def colored(text, color):
    """Apply color to text if terminal supports it."""
    if supports_color():
        return f"{color}{text}{Colors.RESET}"
    return text

def tool_header(tool_name):
    """Format tool execution header like Claude Code."""
    icon = "[TOOL]"
    return colored(f"\n{icon} {tool_name}", Colors.CYAN)

def success_msg(text):
    """Format success message."""
    return colored(f"[OK] {text}", Colors.GREEN)

def error_msg(text):
    """Format error message."""
    return colored(f"[X] {text}", Colors.RED)

def file_path(path, line=None):
    """Format file path as clickable reference."""
    if line:
        formatted = f"{path}:{line}"
    else:
        formatted = path
    return colored(formatted, Colors.BLUE)

def code_block(code, language=""):
    """Format code block with syntax-aware coloring."""
    lines = code.split('\n')
    output = []
    
    for i, line in enumerate(lines, 1):
        line_num = colored(f"{i:4d} │ ", Colors.DIM)
        
        # Simple syntax highlighting
        if language == "python" or code.strip().startswith("def ") or "import " in code:
            # Keywords
            line = re.sub(r'\b(def|class|import|from|return|if|else|elif|for|while|try|except)\b',
                         lambda m: colored(m.group(0), Colors.MAGENTA), line)
            # Strings
            line = re.sub(r'(["\'])(?:(?=(\?))\2.)*?\1',
                         lambda m: colored(m.group(0), Colors.GREEN), line)
            # Comments
            line = re.sub(r'#.*$',
                         lambda m: colored(m.group(0), Colors.BRIGHT_BLACK), line)
        
        output.append(line_num + line)
    
    return '\n'.join(output)

def section_header(title):
    """Format section header."""
    line = "─" * 60
    return f"\n{colored(line, Colors.DIM)}\n{colored(title, Colors.BOLD)}\n{colored(line, Colors.DIM)}"

def spinner_msg(text):
    """Format progress message."""
    spinner = "..."
    return colored(f"{spinner} {text}", Colors.YELLOW)

def format_table(headers, rows):
    """Format data as a table."""
    if not rows:
        return "(no data)"
    
    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Header
    header_row = " │ ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    separator = "─┼─".join("─" * w for w in col_widths)
    
    # Rows
    data_rows = []
    for row in rows:
        data_rows.append(" │ ".join(str(cell).ljust(w) for cell, w in zip(row, col_widths)))
    
    output = [
        colored(header_row, Colors.BOLD),
        colored(separator, Colors.DIM)
    ]
    output.extend(data_rows)
    
    return '\n'.join(output)

def progress_indicator(current, total, width=40):
    """Show progress bar."""
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    percent = int(100 * current / total)
    return f"{colored(bar, Colors.CYAN)} {percent}%"
