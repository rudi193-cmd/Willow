"""Function calling adapter - converts tools to OpenAI function format"""

def tool_to_openai_function(tool_def):
    """Convert ToolDefinition to OpenAI function calling format."""
    properties = {}
    required = []
    
    for param_name, param_type in tool_def.get('parameters', {}).items():
        properties[param_name] = {
            "type": "string" if param_type == "string" else "object",
            "description": f"Parameter {param_name}"
        }
        required.append(param_name)
    
    return {
        "type": "function",
        "function": {
            "name": tool_def['name'],
            "description": tool_def.get('description', ''),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }

def tools_to_openai_format(tools):
    """Convert list of ToolDefinitions to OpenAI format."""
    return [tool_to_openai_function(t) for t in tools]
