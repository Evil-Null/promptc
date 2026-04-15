"""Tests for Claude OAuth/setup token authentication."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from interceptor.adapters.transport import (
    CLAUDE_API_VERSION,
    _CC_BILLING_HEADER,
    _CLAUDE_OAUTH_BETAS,
    _OAUTH_TOKEN_PREFIX,
    _build_claude_headers,
    _inject_billing_attribution,
    _is_oauth_token,
)


class TestOAuthDetection:
    """Token type detection."""

    def test_oauth_token_detected(self) -> None:
        assert _is_oauth_token("sk-ant-oat01-abc123") is True

    def test_standard_key_not_oauth(self) -> None:
        assert _is_oauth_token("sk-ant-api03-abc123") is False

    def test_empty_string_not_oauth(self) -> None:
        assert _is_oauth_token("") is False

    def test_exact_prefix_is_oauth(self) -> None:
        assert _is_oauth_token("sk-ant-oat01-") is True

    def test_random_string_not_oauth(self) -> None:
        assert _is_oauth_token("random-key") is False


class TestBuildClaudeHeaders:
    """Header construction for both auth types."""

    def test_standard_key_uses_x_api_key(self) -> None:
        headers = _build_claude_headers("sk-ant-api03-abc")
        assert "x-api-key" in headers
        assert headers["x-api-key"] == "sk-ant-api03-abc"
        assert "Authorization" not in headers
        assert "anthropic-beta" not in headers

    def test_oauth_token_uses_bearer(self) -> None:
        headers = _build_claude_headers("sk-ant-oat01-abc")
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer sk-ant-oat01-abc"
        assert "x-api-key" not in headers

    def test_oauth_token_has_beta_header(self) -> None:
        headers = _build_claude_headers("sk-ant-oat01-abc")
        assert headers["anthropic-beta"] == _CLAUDE_OAUTH_BETAS

    @pytest.mark.parametrize(
        "key",
        ["sk-ant-api03-abc", "sk-ant-oat01-abc"],
    )
    def test_both_have_version(self, key: str) -> None:
        headers = _build_claude_headers(key)
        assert headers["anthropic-version"] == CLAUDE_API_VERSION

    @pytest.mark.parametrize(
        "key",
        ["sk-ant-api03-abc", "sk-ant-oat01-abc"],
    )
    def test_both_have_content_type(self, key: str) -> None:
        headers = _build_claude_headers(key)
        assert headers["content-type"] == "application/json"


class TestBillingAttribution:
    """Billing attribution injection into system prompt."""

    def test_standard_key_no_injection(self) -> None:
        payload = {"system": "You are helpful.", "model": "claude-sonnet-4-6"}
        result = _inject_billing_attribution(payload, "sk-ant-api03-abc")
        assert result["system"] == "You are helpful."

    def test_oauth_prepends_billing_to_string_system(self) -> None:
        payload = {"system": "You are helpful.", "model": "claude-sonnet-4-6"}
        result = _inject_billing_attribution(payload, "sk-ant-oat01-abc")
        assert result["system"].startswith(_CC_BILLING_HEADER)
        assert "You are helpful." in result["system"]

    def test_oauth_empty_system_still_has_billing(self) -> None:
        payload = {"system": "", "model": "claude-sonnet-4-6"}
        result = _inject_billing_attribution(payload, "sk-ant-oat01-abc")
        assert result["system"] == _CC_BILLING_HEADER

    def test_oauth_missing_system_still_has_billing(self) -> None:
        payload = {"model": "claude-sonnet-4-6"}
        result = _inject_billing_attribution(payload, "sk-ant-oat01-abc")
        assert result["system"] == _CC_BILLING_HEADER

    def test_oauth_list_system_prepends_block(self) -> None:
        payload = {
            "system": [{"type": "text", "text": "You are helpful."}],
            "model": "claude-sonnet-4-6",
        }
        result = _inject_billing_attribution(payload, "sk-ant-oat01-abc")
        assert isinstance(result["system"], list)
        assert result["system"][0] == {"type": "text", "text": _CC_BILLING_HEADER}
        assert result["system"][1]["text"] == "You are helpful."

    def test_original_payload_not_mutated(self) -> None:
        payload = {"system": "Original.", "model": "claude-sonnet-4-6"}
        original_system = payload["system"]
        _inject_billing_attribution(payload, "sk-ant-oat01-abc")
        assert payload["system"] == original_system

    def test_billing_header_format(self) -> None:
        assert "cc_version=" in _CC_BILLING_HEADER
        assert "cc_entrypoint=cli" in _CC_BILLING_HEADER
        assert "cch=00000" in _CC_BILLING_HEADER


class TestSendClaudeWithOAuth:
    """Integration: send_claude uses correct auth for OAuth tokens."""

    @patch("interceptor.adapters.transport._get_api_key")
    def test_send_claude_oauth_headers(self, mock_get_key: MagicMock) -> None:
        mock_get_key.return_value = "sk-ant-oat01-test123"
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "OK"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        mock_client.post.return_value = mock_resp

        from interceptor.adapters.transport import send_claude

        send_claude(
            {"model": "claude-sonnet-4-6", "system": "test", "messages": []},
            client=mock_client,
        )

        call_args = mock_client.post.call_args
        headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")
        assert "x-api-key" not in headers
        assert "oauth-2025-04-20" in headers.get("anthropic-beta", "")

        sent_json = call_args.kwargs.get("json") or call_args[1].get("json")
        assert _CC_BILLING_HEADER in sent_json["system"]

    @patch("interceptor.adapters.transport._get_api_key")
    def test_send_claude_standard_key_headers(
        self, mock_get_key: MagicMock
    ) -> None:
        mock_get_key.return_value = "sk-ant-api03-standard"
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "OK"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        mock_client.post.return_value = mock_resp

        from interceptor.adapters.transport import send_claude

        send_claude(
            {"model": "claude-sonnet-4-6", "system": "test", "messages": []},
            client=mock_client,
        )

        call_args = mock_client.post.call_args
        headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
        assert "x-api-key" in headers
        assert "Authorization" not in headers

        sent_json = call_args.kwargs.get("json") or call_args[1].get("json")
        assert _CC_BILLING_HEADER not in sent_json.get("system", "")
