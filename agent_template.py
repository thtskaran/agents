# agent_template.py
from agno.agent import Agent
from agno.models.groq import Groq
import os
import sys
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load .env from the main project directory if needed (adjust path if necessary)
# This assumes the agent script is run from the project root or .env is accessible
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(project_root, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
else:
    # Fallback if running directly from agents/ dir and .env is in root
    load_dotenv()


# --- Dynamic Imports ---
{imports}
# --- End Dynamic Imports ---

# --- Dynamic Tools ---
agent_tools = [
    {tools}
]
# --- End Dynamic Tools ---

# --- Dynamic Instructions ---
agent_instructions = [
    f"""
You are agent '{agent_id}'. {instructions}
If the prompt is a question, answer it directly.
If the prompt is a request for information, provide the requested information.
    """
]
# --- End Dynamic Instructions ---


agent = Agent(
    model=Groq(
        id="llama-3.1-8b-instant", # Or make this configurable per agent later
        api_key=os.getenv("GROQ_API_KEY"),
    ),
    tools=agent_tools,
    show_tool_calls=True,
    instructions=agent_instructions,
    add_datetime_to_instructions=True,
)

app = Flask(__name__)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data or "prompt" not in data:
        return jsonify({"error": "Missing 'prompt' in request body"}), 400

    prompt = data["prompt"]
    try:
        response = agent.run(prompt).content
        return jsonify({"response": response})
    except Exception as e:
        print(f"Error during agent run: {e}", file=sys.stderr) # Log error
        return jsonify({"error": "Agent failed to process the request"}), 500

@app.route("/health", methods=["GET"])
def health_check():
    # Simple health check endpoint
    return jsonify({"status": "running", "agent_id": "{agent_id}"}), 200


if __name__ == "__main__":
    # Port is passed via environment variable set by the main app
    port = int(os.getenv("FLASK_PORT", 5001)) # Default if not set
    print(f"Starting agent '{agent_id}' on port {port}...")
    # Use host='0.0.0.0' to make it accessible externally if needed
    app.run(host='0.0.0.0', port=port) # Removed debug=True for agent processes