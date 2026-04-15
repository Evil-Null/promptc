"""Audit tests — YamlValidator, CodeValidator, registry integration.

Validates the two new validators plus their registration and format
inference.  All deterministic, network-free.
"""

from __future__ import annotations

import pytest

from interceptor.validation.models import ValidationStatus
from interceptor.validation.registry import get_validator, infer_format
from interceptor.validation.validators import CodeValidator, YamlValidator


# ── A. YamlValidator ──────────────────────────────────────────────────────


class TestYamlValidator:
    """A — YAML format compliance (heuristic)."""

    def _validate(self, text: str) -> object:
        return YamlValidator().validate(text, "")

    def test_valid_yaml_mapping(self) -> None:
        text = "name: Alice\nage: 30\ncity: Tbilisi"
        r = self._validate(text)
        assert r.status == ValidationStatus.PASS
        assert r.score == 1.0
        assert r.issues == []

    def test_valid_yaml_list(self) -> None:
        text = "- item one\n- item two\n- item three"
        r = self._validate(text)
        assert r.status == ValidationStatus.PASS

    def test_valid_yaml_nested(self) -> None:
        text = "server:\n  host: localhost\n  port: 8080"
        r = self._validate(text)
        assert r.status == ValidationStatus.PASS

    def test_empty_input(self) -> None:
        r = self._validate("")
        assert r.status == ValidationStatus.FAIL
        assert r.score == 0.0
        assert any(i.rule == "non_empty" for i in r.issues)

    def test_whitespace_only(self) -> None:
        r = self._validate("   \n  \n  ")
        assert r.status == ValidationStatus.FAIL
        assert r.score == 0.0

    def test_bare_scalar_fails_structure(self) -> None:
        r = self._validate("just a plain string without structure")
        assert any(i.rule == "has_structure" for i in r.issues)

    def test_json_rejected(self) -> None:
        r = self._validate('{"key": "value"}')
        assert any(i.rule == "valid_yaml" for i in r.issues)

    def test_json_array_rejected(self) -> None:
        r = self._validate('[1, 2, 3]')
        assert any(i.rule == "valid_yaml" for i in r.issues)

    def test_code_fenced_yaml(self) -> None:
        text = "```yaml\nname: Bob\nrole: admin\n```"
        r = self._validate(text)
        assert r.status == ValidationStatus.PASS

    def test_mixed_mapping_and_list(self) -> None:
        text = "items:\n  - first\n  - second\ncount: 2"
        r = self._validate(text)
        assert r.status == ValidationStatus.PASS

    def test_validator_name(self) -> None:
        r = self._validate("key: value")
        assert r.validator_name == "yaml"


# ── B. CodeValidator ──────────────────────────────────────────────────────


class TestCodeValidator:
    """B — Code format compliance."""

    def _validate(self, text: str) -> object:
        return CodeValidator().validate(text, "")

    def test_valid_fenced_code_block(self) -> None:
        text = "```python\ndef hello():\n    return 'world'\n```"
        r = self._validate(text)
        assert r.status == ValidationStatus.PASS
        assert r.score == 1.0

    def test_valid_fenced_js(self) -> None:
        text = "```js\nconst x = 1;\nfunction foo() { return x; }\n```"
        r = self._validate(text)
        assert r.status == ValidationStatus.PASS

    def test_raw_code_without_fence(self) -> None:
        text = (
            "def greet(name):\n"
            "    if name:\n"
            "        return f'Hello {name}'\n"
            "    else:\n"
            "        return 'Hello'"
        )
        r = self._validate(text)
        assert not any(i.rule == "has_code_block" for i in r.issues)

    def test_empty_input(self) -> None:
        r = self._validate("")
        assert r.status == ValidationStatus.FAIL
        assert r.score == 0.0
        assert any(i.rule == "non_empty" for i in r.issues)

    def test_no_code_at_all(self) -> None:
        r = self._validate("Just a short note.")
        assert any(i.rule == "has_code_block" for i in r.issues)

    def test_prose_only(self) -> None:
        text = "\n".join(
            [
                "This is a paragraph of text about programming.",
                "Python is a great language for many tasks.",
                "Learning to code takes dedication and practice.",
                "Software engineering is a rewarding career path.",
                "The quick brown fox jumps over the lazy dog.",
            ]
        )
        r = self._validate(text)
        assert any(i.rule == "not_prose" for i in r.issues)

    def test_code_block_not_flagged_as_prose(self) -> None:
        text = "```python\nimport os\ndef main():\n    return os.getcwd()\n```"
        r = self._validate(text)
        assert not any(i.rule == "not_prose" for i in r.issues)

    def test_mixed_code_and_explanation(self) -> None:
        text = (
            "Here is the function:\n\n"
            "```python\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```\n\n"
            "It adds two numbers."
        )
        r = self._validate(text)
        assert not any(i.rule == "has_code_block" for i in r.issues)

    def test_validator_name(self) -> None:
        r = self._validate("```\nx\n```")
        assert r.validator_name == "code"


# ── C. Registry integration ───────────────────────────────────────────────


class TestRegistry:
    """C — YamlValidator and CodeValidator are registered."""

    def test_yaml_registered(self) -> None:
        v = get_validator("yaml")
        assert isinstance(v, YamlValidator)

    def test_code_registered(self) -> None:
        v = get_validator("code")
        assert isinstance(v, CodeValidator)

    def test_get_validator_yaml_works(self) -> None:
        v = get_validator("yaml")
        r = v.validate("key: value", "")
        assert r.validator_name == "yaml"

    def test_get_validator_code_works(self) -> None:
        v = get_validator("code")
        r = v.validate("```py\nx=1\n```", "")
        assert r.validator_name == "code"

    def test_unknown_still_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown output format"):
            get_validator("xml")


# ── D. infer_format detection ─────────────────────────────────────────────


class TestInferFormat:
    """D — Format inference for yaml and code keywords."""

    def test_yaml_keyword(self) -> None:
        assert infer_format("Return YAML config") == "yaml"

    def test_yml_keyword(self) -> None:
        assert infer_format("Output as YML") == "yaml"

    def test_yaml_case_insensitive(self) -> None:
        assert infer_format("Provide a Yaml mapping") == "yaml"

    def test_code_keyword(self) -> None:
        assert infer_format("Return the code") == "code"

    def test_snippet_keyword(self) -> None:
        assert infer_format("Provide a snippet") == "code"

    def test_implementation_keyword(self) -> None:
        assert infer_format("Write the implementation") == "code"

    def test_json_still_works(self) -> None:
        assert infer_format("Return a JSON object") == "json"

    def test_table_still_works(self) -> None:
        assert infer_format("Markdown table of results") == "markdowntable"

    def test_sections_still_works(self) -> None:
        assert infer_format("Structured sections") == "sections"

    def test_numbered_list_still_works(self) -> None:
        assert infer_format("Return a numbered list") == "numberedlist"

    def test_freeform_default(self) -> None:
        assert infer_format("Do whatever") == "freeform"

    def test_empty_string(self) -> None:
        assert infer_format("") == "freeform"
