import sys, os, json
sys.path.insert(0, r"D:\01_Job\Tool\Hermes Agent")
os.environ.setdefault("HERMES_HOME", r"C:\Users\mtk12265\.hermes")

from run_agent import AIAgent

tools = [{
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Returns the current time as HH:MM",
        "parameters": {"type": "object", "properties": {}},
    },
}]

agent = AIAgent(
    provider="aide-responses",
    model="databricks/glm-5-3",
    enabled_toolsets=[],   # no model tools; we inject our own below
    quiet_mode=True,
    skip_context_files=True,
    skip_memory=True,
    platform="cli",
)
agent.tools = tools  # minimal tool surface for the probe

result = agent.run_conversation(
    "Use the get_time tool, then reply with exactly: TOOL-OK <time you got>",
    system_message="You are a test agent. Use the provided tool when asked.",
)
print("FINAL:", result.get("final_response"))
