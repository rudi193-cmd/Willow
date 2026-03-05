"""
GENERATE_TOOL.PY - Meta-tool to scaffold new utilities via free LLMs
=====================================================================
Describe what you want, get a working tool. Uses free LLM fleet.

Usage:
    python tools/generate_tool.py "lint_fixer" "Auto-fix common linting errors in Python files"
    python tools/generate_tool.py "sql_explain" "Explain SQL queries in plain English" --test
"""

import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge_ring.llm_router import ask, TaskType

TOOLS_DIR = Path(__file__).parent

TEMPLATE = '''"""
{NAME_UPPER}.PY - {description}
{'=' * (len(name) + 6 + len(description))}

Usage:
    python tools/{name}.py [args]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge_ring.llm_router import ask, TaskType

# TODO: Implement {name}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="{description}")
    # Add arguments here
    args = parser.parse_args()

    print("Not implemented yet")


if __name__ == "__main__":
    main()
'''

PROMPT = """Generate a complete Python CLI tool with this specification:

Name: {name}
Description: {description}

Requirements:
1. Use argparse for CLI arguments
2. Import and use `from bridge_ring.llm_router import ask, TaskType` for any LLM calls
3. Include helpful docstring at top with usage examples
4. Handle errors gracefully
5. Be concise but functional

Reference these existing tools for style:
- commit_msg.py: generates commit messages from git diff
- error_explain.py: pipes error text to LLM for explanation
- auto_docstrings.py: AST parsing + LLM to add docstrings

Generate ONLY the Python code, no markdown fences or explanation.
Start with the triple-quoted docstring."""


def generate_tool(name: str, description: str) -> str:
    """Generate tool code using free LLM."""
    prompt = PROMPT.format(name=name, description=description)

    response = ask(prompt, TaskType.CODE, max_tokens=4096)

    if response:
        code = response.content.strip()
        # Clean up markdown if present
        if code.startswith('```python'):
            code = code[9:]
        elif code.startswith('```'):
            code = code[3:]
        if code.endswith('```'):
            code = code[:-3]
        return code.strip()

    return None


def validate_code(code: str) -> tuple[bool, str]:
    """Basic validation of generated code."""
    try:
        compile(code, '<generated>', 'exec')
        return True, "Syntax OK"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"


def test_tool(filepath: Path) -> tuple[bool, str]:
    """Run basic test on generated tool."""
    import subprocess
    result = subprocess.run(
        ['python', str(filepath), '--help'],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        return True, result.stdout[:200]
    return False, result.stderr[:200]


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate new tools using free LLM fleet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tools/generate_tool.py sql_explain "Explain SQL queries in plain English"
    python tools/generate_tool.py lint_fixer "Auto-fix Python linting errors" --test
    python tools/generate_tool.py api_mock "Generate mock API responses from OpenAPI spec"
        """
    )
    parser.add_argument('name', help='Tool name (snake_case, no .py)')
    parser.add_argument('description', help='What the tool does')
    parser.add_argument('--test', '-t', action='store_true', help='Test after generation')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Show but do not save')
    parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing')
    args = parser.parse_args()

    # Validate name
    name = args.name.lower().replace('-', '_').replace('.py', '')
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        print(f"Invalid tool name: {name}")
        print("Use snake_case, start with letter")
        return 1

    filepath = TOOLS_DIR / f"{name}.py"

    if filepath.exists() and not args.force:
        print(f"Tool already exists: {filepath}")
        print("Use --force to overwrite")
        return 1

    print(f"Generating: {name}")
    print(f"Description: {args.description}")
    print(f"Using free LLM fleet...\n")

    code = generate_tool(name, args.description)

    if not code:
        print("Failed to generate tool.")
        return 1

    # Validate
    valid, msg = validate_code(code)
    if not valid:
        print(f"Generated code has errors: {msg}")
        print("\nGenerated code:")
        print("-" * 40)
        print(code[:500])
        print("-" * 40)
        return 1

    print(f"Generated {len(code)} bytes, syntax OK")

    if args.dry_run:
        print("\n" + "=" * 60)
        print(code)
        print("=" * 60)
        print("\n(dry run - not saved)")
        return 0

    # Save
    filepath.write_text(code, encoding='utf-8')
    print(f"Saved: {filepath}")

    # Test
    if args.test:
        print("\nTesting...")
        success, output = test_tool(filepath)
        if success:
            print("Test passed!")
            print(output[:200])
        else:
            print(f"Test failed: {output}")
            return 1

    print(f"\nTool ready: python tools/{name}.py --help")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
