import sys, json as J, time
sys.path.insert(0, r"D:\01_Job\Tool\Hermes Agent")

from hermes_cli.runtime_provider import resolve_runtime_provider
from run_agent import AIAgent
from tools.registry import registry

registry.register(
    name="get_time",
    toolset="probe",
    schema={"name": "get_time", "description": "Returns current time as HH:MM",
            "parameters": {"type": "object", "properties": {}}},
    handler=lambda args, **kw: J.dumps({"time": "23:59"}),
)

out = []
for slug in ["aide-responses-io", "aide-responses-crlogai001", "aide-responses-molycrgpt001"]:
    t0 = time.time()
    try:
        rt = resolve_runtime_provider(requested=slug, target_model="databricks/glm-5-3")
        agent = AIAgent(
            base_url=rt["base_url"], api_key=rt["api_key"], provider="custom",
            api_mode=rt["api_mode"], model="databricks/glm-5-3",
            enabled_toolsets=["probe"], quiet_mode=True,
            skip_context_files=True, skip_memory=True, platform="cli",
            default_headers=rt.get("default_headers") or {},
        )
        res = agent.run_conversation("Use the get_time tool, then reply exactly: TOOL-OK 23:59")
        line = f"{slug} => {str(res.get('final_response'))[:140]}"
    except Exception as e:
        line = f"{slug} => EXC {type(e).__name__}: {str(e)[:120]}"
    print(line, flush=True)
    out.append(line)

with open(r"D:\01_Job\Tool\Hermes Agent\.scratch\dbx_e2e_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
