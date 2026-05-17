import unittest

from demo_config import build_manifest
from skill_catalog import select_skills_for_prompt, skills_for_agent


class SkillCatalogTests(unittest.TestCase):
    def test_tooling_agent_exposes_mermaid_skill(self):
        manifest = build_manifest("tooling")
        skill_names = {skill["name"] for skill in manifest["skills"]}
        self.assertIn("mermaid-diagrams", skill_names)

    def test_mermaid_prompt_selects_diagram_skill(self):
        skills = skills_for_agent("tooling")
        selected = select_skills_for_prompt(skills, "画一个 Mermaid 流程图")
        self.assertEqual(selected[0]["name"], "mermaid-diagrams")


if __name__ == "__main__":
    unittest.main()
