"""
Regression test: TeamsMTKAdapter.edit_message() MUST accept 'content' kwarg.

Root cause: commit 1170ca859 named the parameter 'new_content' instead of
'content' (the name used by BasePlatformAdapter and all callers in
stream_consumer.py / run.py). This caused every progress-stream edit to
fail with: "got unexpected keyword argument 'content'".
"""
import inspect
import pytest


class TestEditMessageSignatureConformance:
    """edit_message must accept the same keyword args as BasePlatformAdapter."""

    def test_edit_message_accepts_content_kwarg(self):
        """Regression: edit_message(chat_id=.., message_id=.., content=..) must not raise."""
        from gateway.platforms.teams_mtk import TeamsMTKAdapter

        sig = inspect.signature(TeamsMTKAdapter.edit_message)
        params = sig.parameters
        # Must have 'content' as a named parameter (not 'new_content' etc.)
        assert "content" in params, (
            f"edit_message missing 'content' param; "
            f"found: {list(params.keys())}. "
            f"All callers pass content=... as a kwarg."
        )

    def test_edit_message_signature_matches_base(self):
        """edit_message param names must match BasePlatformAdapter exactly."""
        from gateway.platforms.base import BasePlatformAdapter
        from gateway.platforms.teams_mtk import TeamsMTKAdapter

        base_sig = inspect.signature(BasePlatformAdapter.edit_message)
        mtk_sig = inspect.signature(TeamsMTKAdapter.edit_message)

        base_params = list(base_sig.parameters.keys())
        mtk_params = list(mtk_sig.parameters.keys())

        # At minimum: self, chat_id, message_id, content
        required = ["self", "chat_id", "message_id", "content"]
        for p in required:
            assert p in mtk_params, (
                f"TeamsMTKAdapter.edit_message missing '{p}'. "
                f"Has: {mtk_params}"
            )

    def test_edit_message_accepts_finalize_kwarg(self):
        """edit_message must accept finalize= kwarg (stream_consumer contract)."""
        from gateway.platforms.teams_mtk import TeamsMTKAdapter

        sig = inspect.signature(TeamsMTKAdapter.edit_message)
        params = sig.parameters
        assert "finalize" in params, (
            f"edit_message missing 'finalize' param; "
            f"found: {list(params.keys())}. "
            f"stream_consumer._edit_message always passes finalize=."
        )

    def test_edit_message_returns_send_result(self):
        """edit_message must return SendResult (not bool)."""
        from gateway.platforms.teams_mtk import TeamsMTKAdapter
        from gateway.platforms.base import SendResult

        sig = inspect.signature(TeamsMTKAdapter.edit_message)
        ret = sig.return_annotation
        # Accept either the string annotation or the actual class
        if isinstance(ret, str):
            assert "SendResult" in ret, (
                f"edit_message return annotation is '{ret}', expected SendResult"
            )
        else:
            assert ret is SendResult, (
                f"edit_message return annotation is {ret}, expected SendResult"
            )

    def test_no_adapter_uses_nonstandard_content_param_name(self):
        """Check ALL adapters: none should use a non-standard param name for content."""
        import importlib, pkgutil
        from gateway.platforms.base import BasePlatformAdapter

        # Scan all known adapter modules
        adapter_paths = [
            "gateway.platforms.teams_mtk",
            "plugins.platforms.telegram.adapter",
            "plugins.platforms.slack.adapter",
            "plugins.platforms.discord.adapter",
            "plugins.platforms.dingtalk.adapter",
            "plugins.platforms.feishu.adapter",
            "plugins.platforms.matrix.adapter",
            "plugins.platforms.mattermost.adapter",
            "plugins.platforms.google_chat.adapter",
            "plugins.platforms.whatsapp.adapter",
        ]
        problems = []
        for mod_path in adapter_paths:
            try:
                mod = importlib.import_module(mod_path)
            except ImportError:
                continue  # not installed, skip
            adapter_cls = None
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePlatformAdapter)
                    and attr is not BasePlatformAdapter
                    and hasattr(attr, "edit_message")
                    and "edit_message" in attr.__dict__  # overrides base
                ):
                    adapter_cls = attr
                    break
            if not adapter_cls:
                continue
            sig = inspect.signature(adapter_cls.edit_message)
            params = list(sig.parameters.keys())
            if "content" not in params:
                problems.append(f"{adapter_cls.__name__}: {params}")
        assert not problems, (
            f"Adapters with non-standard edit_message param names: {problems}"
        )
