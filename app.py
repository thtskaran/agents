# app.py
import os
import subprocess
import json
import uuid
import signal
import time
import sys
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from models import db, Users, Agents, Models # Import from models.py

load_dotenv()

# --- Configuration ---
BASE_AGENT_PORT = 6000 # Starting port for agents
AGENT_DIR = "agents" # Directory to store agent files
AGENT_TEMPLATE_FILE = "agent_template.py"
TOOL_MAPPING_FILE = "mapping.json"

# --- App Initialization ---
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app) # Associate db with the app

# --- Helper Functions ---

# Create agent directory if it doesn't exist
if not os.path.exists(AGENT_DIR):
    os.makedirs(AGENT_DIR)

# Load tool mapping
try:
    with open(TOOL_MAPPING_FILE, 'r') as f:
        tool_mapping = json.load(f)
except FileNotFoundError:
    print(f"Error: {TOOL_MAPPING_FILE} not found. Agent creation will fail for tools.")
    tool_mapping = {}
except json.JSONDecodeError:
    print(f"Error: Could not decode {TOOL_MAPPING_FILE}. Check its format.")
    tool_mapping = {}


def find_available_port(start_port):
    """Finds an available port starting from start_port."""
    running_agents = Agents.query.filter(Agents.status == 'running', Agents.port.isnot(None)).all()
    used_ports = {agent.port for agent in running_agents}
    port = start_port
    while port in used_ports or is_port_in_use(port): # Check DB and system
        port += 1
        if port > 65535:
            raise Exception("No available ports found.")
    return port

def is_port_in_use(port):
    """Check if a port is actively in use on the system (basic check)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            # Try to bind to the port on localhost
            s.bind(("127.0.0.1", port))
            return False # Port is available
        except socket.error:
            return True # Port is likely in use


# --- Agent Management Routes ---

@app.route("/agents", methods=["POST"])
def create_agent():
    """Creates a new agent definition and its .py file."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    user_id = data.get("userId")
    permissions = data.get("permissions", []) # List of permission names like ["DuckDuckGo", "Arxiv"]
    description = data.get("description", "")
    name = data.get("name", "Untitled Agent")
    instructions = data.get("instructions", "You are a helpful AI assistant.") # Base instructions
    pcode = data.get("pcode") # Get pcode from request data

    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    # Validate user exists (optional but recommended)
    user = Users.query.get(user_id)
    if not user:
        return jsonify({"error": f"User with id {user_id} not found"}), 404

    # Generate unique agent ID and file path
    agent_id = uuid.uuid4().hex[:10] # Shorter unique ID
    file_path = os.path.join(AGENT_DIR, f"{agent_id}.py")

    # --- Generate Agent Code ---
    try:
        with open(AGENT_TEMPLATE_FILE, 'r') as f_template:
            template_code = f_template.read()

        imports_code = []
        tools_code = []
        valid_permissions = []

        for perm_name in permissions:
            if perm_name in tool_mapping:
                mapping = tool_mapping[perm_name]
                imports_code.append(mapping["import"])
                tools_code.append(f"    {mapping['tool']},") # Indented for list
                valid_permissions.append(perm_name)
            else:
                print(f"Warning: Permission '{perm_name}' not found in mapping.json. Skipping.")

        # Format for insertion into template
        imports_str = "\n".join(imports_code)
        tools_str = "\n".join(tools_code)

        # Replace placeholders
        agent_code = template_code.replace("{imports}", imports_str)
        agent_code = agent_code.replace("{tools}", tools_str)
        agent_code = agent_code.replace("{instructions}", instructions.replace('"', '\\"')) # Basic escaping for instructions
        agent_code = agent_code.replace("{agent_id}", agent_id)


        # Write the generated code to the agent's file
        with open(file_path, 'w') as f_agent:
            f_agent.write(agent_code)
        print(f"Generated agent file: {file_path}")

    except Exception as e:
        print(f"Error generating agent file for {agent_id}: {e}", file=sys.stderr)
        return jsonify({"error": f"Failed to generate agent file: {e}"}), 500
    # --- End Generate Agent Code ---

    # --- Create Agent Record in DB ---
    try:
        new_agent = Agents(
            agentid=agent_id,
            userId=user_id,
            name=name,
            description=description,
            permissions=json.dumps(valid_permissions), # Store valid permissions as JSON list
            pcode=pcode, # Add pcode to the new agent
            instructions=instructions,
            file_path=file_path,
            status='created' # Initial status
        )
        db.session.add(new_agent)
        db.session.commit()

        return jsonify({
            "message": "Agent created successfully",
            "agent": new_agent.to_dict() # Return the created agent data
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"Error saving agent {agent_id} to database: {e}", file=sys.stderr)
        # Clean up generated file if DB save fails
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Cleaned up file: {file_path}")
            except OSError as rm_err:
                print(f"Error cleaning up file {file_path}: {rm_err}", file=sys.stderr)
        return jsonify({"error": f"Failed to save agent to database: {e}"}), 500
    # --- End Create Agent Record ---


@app.route("/agents", methods=["GET"])
def get_all_agents():
    """Gets a list of all agents."""
    agents = Agents.query.all()
    return jsonify([agent.to_dict() for agent in agents])

@app.route("/agents/<string:agent_id>", methods=["GET"])
def get_agent(agent_id):
    """Gets details for a specific agent."""
    agent = Agents.query.filter_by(agentid=agent_id).first()
    if not agent:
        return jsonify({"message": "Agent not found"}), 404
    return jsonify(agent.to_dict())


@app.route("/agents/<string:agent_id>/start", methods=["POST"])
def start_agent(agent_id):
    """Starts the agent's Flask server in a subprocess."""
    agent = Agents.query.filter_by(agentid=agent_id).first()
    if not agent:
        return jsonify({"message": "Agent not found"}), 404

    if agent.status == 'running' and agent.pid:
        # Check if the process actually exists
        try:
            os.kill(agent.pid, 0) # Check if process exists without killing
            print(f"Agent {agent_id} already running with PID {agent.pid} on port {agent.port}")
            return jsonify({"message": f"Agent {agent_id} is already running", "port": agent.port}), 200
        except OSError:
            print(f"Agent {agent_id} status is 'running' but PID {agent.pid} not found. Resetting.")
            agent.status = 'error' # Or 'stopped'
            agent.pid = None
            agent.port = None
            db.session.commit()
            # Proceed to start again

    if not os.path.exists(agent.file_path):
         return jsonify({"error": f"Agent file {agent.file_path} not found."}), 404

    try:
        port = find_available_port(BASE_AGENT_PORT)
    except Exception as e:
        print(f"Error finding port for agent {agent_id}: {e}", file=sys.stderr)
        return jsonify({"error": str(e)}), 500

    # Environment variables for the subprocess
    agent_env = os.environ.copy()
    agent_env["FLASK_PORT"] = str(port)
    # Make sure GROQ key is passed (or any other needed keys)
    agent_env["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "") # Pass it explicitly

    command = [sys.executable, agent.file_path] # Use sys.executable for portability

    try:
        print(f"Starting agent {agent_id} with command: {' '.join(command)} on port {port}")

        # Use Popen for non-blocking execution
        # On Linux/macOS, preexec_fn=os.setsid creates a new session, easier to kill group later if needed
        # On Windows, use creationflags or default behavior
        preexec_fn = None
        creationflags = 0
        if os.name == 'posix':
            preexec_fn = os.setsid
        elif os.name == 'nt':
            # Example: DETACHED_PROCESS allows parent to exit independently
            # creationflags = subprocess.DETACHED_PROCESS
            pass # Default flags often sufficient

        process = subprocess.Popen(
            command,
            env=agent_env,
            preexec_fn=os.setsid if os.name == 'posix' else None,
            creationflags=creationflags,
            # Only close non-standard file descriptors
            close_fds=False if sys.platform == 'darwin' else True,
            # Remove this as it conflicts with preexec_fn on some platforms
            # start_new_session=True,
        )
        # You could implement a more robust check (e.g., try connecting to agent's /health)
        time.sleep(2)

        # Check if process started successfully (optional, basic check)
        if process.poll() is not None: # Process terminated immediately
             raise Exception(f"Agent process failed to start. Exit code: {process.poll()}")


        agent.status = 'running'
        agent.pid = process.pid
        agent.port = port
        db.session.commit()

        print(f"Agent {agent_id} started successfully. PID: {agent.pid}, Port: {port}")
        return jsonify({
            "message": f"Agent {agent_id} started successfully",
            "agent_id": agent.agentid,
            "port": port,
            "pid": agent.pid
        }), 200

    except Exception as e:
        print(f"Error starting agent {agent_id}: {e}", file=sys.stderr)
        agent.status = 'error'
        agent.pid = None
        agent.port = None
        db.session.commit()
        return jsonify({"error": f"Failed to start agent: {e}"}), 500


@app.route("/agents/<string:agent_id>/stop", methods=["POST"])
def stop_agent(agent_id):
    """Stops the agent's running process."""
    agent = Agents.query.filter_by(agentid=agent_id).first()
    if not agent:
        return jsonify({"message": "Agent not found"}), 404

    if agent.status != 'running' or not agent.pid:
        # If status is running but no PID, something is wrong. Fix it.
        if agent.status == 'running' and not agent.pid:
            agent.status = 'stopped' # Or 'error'
            agent.port = None
            db.session.commit()
            return jsonify({"message": f"Agent {agent_id} had inconsistent state (running but no PID). Status reset to stopped."}), 200
        return jsonify({"message": f"Agent {agent_id} is not running."}), 200

    pid_to_kill = agent.pid
    print(f"Attempting to stop agent {agent_id} with PID {pid_to_kill}...")

    try:
        # Try terminating gracefully first
        if os.name == 'posix':
             # Kill the entire process group started with os.setsid
             os.killpg(os.getpgid(pid_to_kill), signal.SIGTERM)
        elif os.name == 'nt':
             # Windows: Use taskkill
             subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid_to_kill)], check=True, capture_output=True)
             # os.kill(pid_to_kill, signal.SIGTERM) # SIGTERM might not be forceful enough on Windows often

        # Wait a moment for the process to terminate
        time.sleep(1)

        # Check if it's still alive
        try:
            os.kill(pid_to_kill, 0) # Check if process exists
            # If it exists, force kill (use SIGKILL on POSIX)
            print(f"Process {pid_to_kill} still alive after SIGTERM. Force killing.")
            if os.name == 'posix':
                os.killpg(os.getpgid(pid_to_kill), signal.SIGKILL)
            # taskkill with /F already force kills on Windows
        except OSError:
            # Process already terminated
            pass

        print(f"Successfully sent termination signal to PID {pid_to_kill} for agent {agent_id}.")

    except ProcessLookupError:
        print(f"Process with PID {pid_to_kill} not found. It might have already stopped.")
    except Exception as e:
        print(f"Error stopping process {pid_to_kill} for agent {agent_id}: {e}", file=sys.stderr)
        # Still update status in DB, but report potential issue
        agent.status = 'error' # Indicate potential issue
        agent.pid = None
        agent.port = None
        db.session.commit()
        return jsonify({"error": f"An error occurred while trying to stop the agent process: {e}"}), 500

    # Update database record
    agent.status = 'stopped'
    agent.pid = None
    agent.port = None
    db.session.commit()

    return jsonify({"message": f"Agent {agent_id} stopped successfully."}), 200


# --- User and Model Routes (from original prompt, slightly adapted) ---

@app.route("/users", methods=["GET"])
def get_all_users():
    # Using the to_dict method from the model for consistency
    users = Users.query.all()
    return jsonify([user.to_dict() for user in users])

# Add POST /users for creation (ensure password hashing!)

@app.route("/users/<int:user_id>/agents", methods=["GET"])
def get_agents_by_user(user_id):
    user = Users.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    agents = Agents.query.filter_by(userId=user_id).all()
    return jsonify([agent.to_dict() for agent in agents])


@app.route("/models", methods=["GET"])
def get_all_models():
    models = Models.query.all()
    return jsonify([model.to_dict() for model in models])

@app.route("/models", methods=["POST"])
def create_model():
    data = request.get_json()
    if not data or not data.get('name') or not data.get('code') or not data.get('provider'):
         return jsonify({"error": "Missing required fields: name, code, provider"}), 400

    new_model = Models(
        name=data["name"],
        code=data["code"],
        provider=data["provider"],
        offline=data.get("offline", False),
        endpoint=data.get("endpoint"),
    )
    try:
        db.session.add(new_model)
        db.session.commit()
        return jsonify({"message": "Model created successfully", "model": new_model.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        # Could be IntegrityError if 'code' is not unique
        return jsonify({"error": f"Failed to create model: {e}"}), 500


@app.route("/models/<int:model_id>", methods=["GET"])
def get_model(model_id):
    model = Models.query.get_or_404(model_id)
    return jsonify(model.to_dict())

# --- Main Execution ---

if __name__ == "__main__":
    with app.app_context():
        print("Creating database tables if they don't exist...")
        db.create_all()
        print("Database tables checked/created.")
    # Port for the main management API server
    management_port = int(os.getenv("MANAGEMENT_PORT", 5000))
    print(f"Starting Management API server on port {management_port}...")
    app.run(host='0.0.0.0', port=management_port, debug=os.getenv("FLASK_DEBUG") == '1')