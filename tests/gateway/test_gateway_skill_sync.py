import inspect

from gateway.run import start_gateway


def test_gateway_runtime_uses_guarded_startup_skill_sync():
    source = inspect.getsource(start_gateway)

    assert "_sync_bundled_skills_for_startup" in source
    assert "from tools.skills_sync import sync_skills" not in source
