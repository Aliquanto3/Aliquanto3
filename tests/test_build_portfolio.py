import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_portfolio as bp  # noqa: E402

CFG = {
    "topic": "ai-portfolio",
    "headers": {"fr": ["Projet", "État", "Description"], "en": ["Project", "Status", "Description"]},
    "statuses": {
        "status-deployed": {"fr": "Déployé", "en": "Deployed", "with_version": True, "rank": 1},
        "status-dev": {"fr": "En dev", "en": "In dev", "rank": 2},
    },
    "release_default": "status-deployed",
    "pending": {"fr": "{tag} à tester", "en": "{tag} pending"},
    "unknown": {"fr": "Inconnu", "en": "Unknown"},
    "repos": {
        "zeta": {"name": "Zeta", "en": "Zeta en"},
        "beta": {"name": "Beta", "name_en": "Beta EN", "en": "a|b\nc"},
    },
}


def repo(name, topics=(), release=None, private=False, desc="d"):
    return {"name": name, "url": f"https://x/{name}", "private": private,
            "description": desc, "topics": ["ai-portfolio", *topics], "release": release}


class T(unittest.TestCase):
    def table(self, repos, lang="fr"):
        err = io.StringIO()
        with redirect_stderr(err):
            out = bp.render_table(bp.select_repos(repos, CFG), CFG, lang)
        return out, err.getvalue()

    def test_public_link_private_no_link(self):
        out, _ = self.table([repo("a"), repo("b", private=True)])
        self.assertIn("[a](https://x/a)", out)
        self.assertIn("🔒 b", out)
        self.assertNotIn("https://x/b", out)

    def test_status_version_and_release_default(self):
        out, _ = self.table([repo("a", ["status-deployed"], "v1"), repo("b", release="v2")])
        self.assertIn("Déployé · v1", out)
        self.assertIn("Déployé · v2", out)

    def test_no_version_ignores_release(self):
        out, _ = self.table([repo("a", ["status-dev"], "v1")])
        self.assertIn("En dev |", out)
        self.assertNotIn("v1", out)

    def test_prerelease_display(self):
        pre = {**repo("a", ["status-deployed"], "v1"), "prerelease": "v2"}
        only = {**repo("b", ["status-deployed"]), "prerelease": "v3"}
        for lang, txt in (("fr", "à tester"), ("en", "pending")):
            out, _ = self.table([pre, only], lang)
            self.assertIn(f"v1 · v2 {txt}", out)
            self.assertIn(f"· v3 {txt}", out)
            self.assertNotIn(f"v1 · v3", out)

    def test_prerelease_ignored_without_version_and_default(self):
        out, _ = self.table([{**repo("a", ["status-dev"]), "prerelease": "v2"}])
        self.assertNotIn("v2", out)
        out, _ = self.table([{**repo("b"), "prerelease": "v2"}])
        self.assertIn("Déployé · v2 à tester", out)

    def test_missing_prerelease_key(self):
        out, _ = self.table([repo("a", ["status-deployed"], "v1")])
        self.assertIn("Déployé · v1 |", out)

    def test_unknown_status_warns(self):
        out, err = self.table([repo("a")])
        self.assertIn("Inconnu", out)
        self.assertIn("avertissement", err)
        self.assertIn("a", err.split("avertissement", 1)[1])

    def test_status_priority_follows_config_order(self):
        out, _ = self.table([repo("a", ["status-dev", "status-deployed"], "v2")])
        self.assertIn("Déployé · v2", out)

    def test_no_selected_repo_is_an_error(self):
        with self.assertRaises(RuntimeError):
            bp.build("rien", [{**repo("x"), "topics": []}], CFG)

    def test_filter_and_order(self):
        repos = [repo("zeta", ["status-dev"]), repo("beta", ["status-dev"]),
                 repo("alpha", ["status-dev"]), repo("omega", ["status-deployed"]),
                 repo("nul"), {**repo("x"), "topics": ["other"]}]
        names = [r["name"] for r in bp.select_repos(repos, CFG)]
        self.assertEqual(names, ["omega", "alpha", "beta", "zeta", "nul"])

    def test_alphabetical_ignores_case_and_accents(self):
        cfg = {**CFG, "repos": {"e": {"name": "Écho"}, "d": {"name": "delta"}, "f": {"name": "Foxtrot"}}}
        repos = [repo(n, ["status-dev"]) for n in ("f", "e", "d")]
        self.assertEqual([r["name"] for r in bp.select_repos(repos, cfg)], ["d", "e", "f"])

    def test_order_uses_display_name_of_language(self):
        cfg = {**CFG, "repos": {"j": {"name": "Copilote Jira", "name_en": "Jira Copilot"},
                                "h": {"name": "Harnais", "name_en": "Harness"}}}
        repos = [repo("j", ["status-dev"]), repo("h", ["status-dev"])]
        self.assertEqual([r["name"] for r in bp.select_repos(repos, cfg, "fr")], ["j", "h"])
        self.assertEqual([r["name"] for r in bp.select_repos(repos, cfg, "en")], ["h", "j"])

    def test_name_en_and_escape(self):
        out, _ = self.table([repo("beta", ["status-dev"])], "en")
        self.assertIn("[Beta EN]", out)
        self.assertIn("a\\|b c", out)

    def test_en_fallback_warns(self):
        _, err = self.table([repo("alpha", ["status-dev"])], "en")
        self.assertIn("anglaise", err)

    def test_replace_idempotent(self):
        readme = ("x\n<!-- portfolio:fr:start -->\nold\n<!-- portfolio:fr:end -->\n"
                  "<!-- portfolio:en:start --><!-- portfolio:en:end -->\n")
        with redirect_stderr(io.StringIO()):
            once = bp.build(readme, [repo("zeta", ["status-dev"])], CFG)
            twice = bp.build(once, [repo("zeta", ["status-dev"])], CFG)
        self.assertEqual(once, twice)
        self.assertNotIn("old", once)
        self.assertIn("<!-- portfolio:fr:start -->\n\n|", once)

    def test_missing_marker(self):
        with self.assertRaises(ValueError):
            bp.build("rien", [repo("a")], CFG)


if __name__ == "__main__":
    unittest.main()
