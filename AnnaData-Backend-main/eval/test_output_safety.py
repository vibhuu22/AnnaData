"""Offline regression checks; no database, model or outbound requests."""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import output_guards


class OutputSafety(unittest.TestCase):
    def test_missing_evidence_removes_figures_across_scripts(self):
        for answer in [
            'The MSP is Rs. 9999 per quintal.',
            'गेहूं का न्यूनतम समर्थन मूल्य ९९९९ रुपये प्रति क्विंटल है।',
            'The scheme pays a subsidy of Rs 9999.',
            'इस योजना में 9999 रुपये मिलते हैं।',
            'এই প্রকল্পে 9999 টাকা ভর্তুকি পাবেন।',
            'ਇਸ ਯੋਜਨਾ ਵਿੱਚ 9999 ਰੁਪਏ ਮਿਲਦੇ ਹਨ।',
        ]:
            with self.subTest(answer=answer):
                cleaned, changed = output_guards.scrub(answer, {})
                self.assertTrue(changed)
                self.assertNotIn('9999', cleaned)
                self.assertNotIn('९९९९', cleaned)

    def test_non_numeric_guidance_survives(self):
        text = 'Ask your district office about this scheme.'
        self.assertEqual(output_guards.scrub(text, {}), (text, False))

    def test_retrieved_figures_survive(self):
        text = 'The MSP is Rs 2585 per quintal.'
        self.assertEqual(output_guards.scrub(text, {'msp': text}), (text, False))

    def test_every_agent_result_is_guarded_without_model_imports(self):
        tree = ast.parse((ROOT / 'Agent.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AgentResult')
        scope = {'output_guards': output_guards}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'Agent.py', 'exec'), scope)
        self.assertNotIn('9999', scope['AgentResult']('This scheme pays Rs 9999.').answer)
        supported = 'The MSP is Rs 2585 per quintal.'
        self.assertEqual(scope['AgentResult'](supported, evidence={'msp': supported}).answer, supported)


if __name__ == '__main__':
    unittest.main()
