import sys, json as J
sys.path.insert(0, r"D:\01_Job\Tool\Hermes Agent")
import os
os.environ["HERMES_TUI"] = "1"

# Use the REAL TUI agent-construction path (same function session.new/resume calls)
import tui_gateway.server as S

agent = S._make_agent(
    "probe-sid",
    "probe-key",
    session_id=None,
    session_db=None,
    model_override={"model": "databricks/glm-5-3", "provider": "aide-responses"},
    platform_override=None,
)
print("BUILT model=", getattr(agent, "model", "?"), "api_mode=", getattr(agent, "api_mode", "?"),
      "base_url=", getattr(agent, "base_url", "?"))
res = agent.run_conversation("Reply with exactly: TUI-DBX-CHECK")
print("FINAL:", str(res.get("final_response"))[:200])
