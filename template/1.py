from agno.agent import Agent
from agno.models.groq import Groq
import datetime
import os

from flask import Flask, request, jsonify
#change imports as per the perms

agent = Agent(
    model=Groq(
        id="llama-3.1-8b-instant",
        api_key=os.getenv("GROQ_API_KEY"),
    ),
    tools=[],
    show_tool_calls=True,
    agent = Agent(tools=[], show_tool_calls=True), #add tools in this array
    instructions=[
        f"""
      You are a helpful assistant. You will be given a prompt and you should respond to it.
        If the prompt is a question, answer it directly.
        If the prompt is a request for information, provide the requested information.
        """
    ],
    add_datetime_to_instructions=True,
)

app = Flask(__name__)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data or "prompt" not in data:
        return jsonify({"error": "Missing 'prompt' in request body"}), 400

    prompt = data["prompt"]
    response = agent.run(prompt).content
    return jsonify({"response": response})


if __name__ == "__main__":
    app.run(debug=True)
