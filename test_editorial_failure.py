"""Regression tests without live API requests or publication side effects."""
import ast
import copy
import json
import re
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


def isolated_module():
    tree = ast.parse(Path(__file__).with_name("fetch_news.py").read_text(encoding="utf-8"))
    names = {"validate_editorial", "summarize_editorial_with_gemini", "main"}
    constants = {"EDITORIAL_TEXT_FIELDS", "EDITORIAL_SCHEMA"}
    nodes = [node for node in tree.body if
             (isinstance(node, ast.FunctionDef) and node.name in names) or
             (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets))]
    ns = {"json": json, "re": re, "time": Mock(), "GEMINI_API_KEY": "test-placeholder",
          "editorial_rank": lambda article: 0,
          "types": types.SimpleNamespace(GenerateContentConfig=lambda **kw: kw),
          "genai": Mock()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "fetch_news.py", "exec"), ns)
    return ns


class EditorialFailureTests(unittest.TestCase):
    def setUp(self):
        self.ns = isolated_module()
        self.articles = [{"source": "Test", "title": "Test", "url": "https://example.com/news", "summary": "Test"}]
        self.valid = {key: "本文" for key in self.ns["EDITORIAL_TEXT_FIELDS"]}
        self.valid.update(company_positions=[], next_signals=["観測点"], sources=[{"title": "Test", "url": self.articles[0]["url"]}])
        self.api = self.ns["genai"].Client.return_value.models.generate_content

    def response(self, value, reason="STOP"):
        return types.SimpleNamespace(text=value, candidates=[types.SimpleNamespace(finish_reason=reason)])

    def test_invalid_json_retried_then_success(self):
        self.api.side_effect = [self.response('{"headline":"bad"'), self.response(json.dumps(self.valid))]
        result = self.ns["summarize_editorial_with_gemini"](self.articles)
        self.assertTrue(result["joho_picks"])
        self.assertEqual(self.api.call_count, 2)
        self.assertEqual(self.api.call_args.kwargs["config"]["response_schema"], self.ns["EDITORIAL_SCHEMA"])

    def test_exhausted_retries_raise(self):
        self.api.return_value = self.response("broken")
        with self.assertRaisesRegex(RuntimeError, "3回失敗"):
            self.ns["summarize_editorial_with_gemini"](self.articles)
        self.assertEqual(self.api.call_count, 3)

    def test_truncated_response_is_not_published_even_if_json_parses(self):
        self.api.return_value = self.response(json.dumps(self.valid), "MAX_TOKENS")
        with self.assertRaises(RuntimeError):
            self.ns["summarize_editorial_with_gemini"](self.articles)

    def test_schema_and_source_validation(self):
        for field, value in [("opening", ""), ("sources", []), ("next_signals", "bad"),
                             ("sources", [{"title": "bad", "url": "https://unknown.example"}])]:
            broken = copy.deepcopy(self.valid)
            broken[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.ns["validate_editorial"](broken, self.articles)

    def test_missing_key_does_not_call_api(self):
        self.ns["GEMINI_API_KEY"] = ""
        with self.assertRaisesRegex(RuntimeError, "未設定"):
            self.ns["summarize_editorial_with_gemini"](self.articles)
        self.api.assert_not_called()

    def test_main_never_saves_or_archives_when_generation_fails(self):
        self.ns.update(log=Mock(), fetch_articles=Mock(return_value=self.articles))
        for name in ["load_history", "archive_current_page", "save_data", "generate_html", "upload_to_ftp"]:
            self.ns[name] = Mock()
        self.api.return_value = self.response("broken")
        with self.assertRaises(RuntimeError):
            self.ns["main"]()
        for name in ["archive_current_page", "save_data", "generate_html", "upload_to_ftp"]:
            self.ns[name].assert_not_called()


if __name__ == "__main__":
    unittest.main()
