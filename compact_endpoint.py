from flask import Flask, request, jsonify
from marshmallow import Schema, fields

app = Flask(__name__)

# Define the schema for the request data
class CompactRequestSchema(Schema):
    task_id = fields.String(required=True)
    action = fields.String(required=True)
    params = fields.Dict()

# Create a Flask application

compact_request_schema = CompactRequestSchema()

# Mapping of actions to agents
agents = {
    'action1': {'agent': 'agent1', 'params': ['param1', 'param2']},
    'action2': {'agent': 'agent2', 'params': ['param3', 'param4']}
}

# Create a response message class with marshmallow schemas
class CompactResponseSchema(Schema):
    agent = fields.String()
    result = fields.String()
    error = fields.String()

# Define the endpoint for compact requests
@app.route('/api/agents/compact', methods=['POST'])
def compact_request():
    try:
        # Parse the request body to a dict
        data = compact_request_schema.load(request.json)
        
        # Get the task ID, action, and agent params
        task_id = data['task_id']
        action = data['action']
        params = data['params']
        
        # Get the agent for the action
        agent = agents.get(action, {}).get('agent')
        agent_params = agents.get(action, {}).get('params', [])
        
        # Check if the agent and params are valid
        if agent and set(agent_params) == set(params):
            # Create a response message
            response_schema = CompactResponseSchema()
            response = response_schema.load({
                'agent': agent,
                'result': 'Success'
            })
        else:
            # Create a response message with an error
            response_schema = CompactResponseSchema()
            response = response_schema.load({
                'error': 'Invalid or missing parameters'
            })
    except Exception as e:
        # Create a response message with an error
        response_schema = CompactResponseSchema()
        response = response_schema.load({
            'error': str(e)
        })
    
    # Return the response
    return jsonify(response), 200

if __name__ == "__main__":
    app.run(debug=True)
