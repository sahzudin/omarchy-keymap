from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from contextlib import redirect_stdout
from io import StringIO


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("keymap", ROOT / "scripts/keymap.py")
keymap = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(keymap)


class KeymapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.env = mock.patch.dict(os.environ, {
            "OMARCHY_KEYMAP_HOME": str(self.home),
            "OMARCHY_KEYMAP_OMARCHY_PATH": str(self.home / "omarchy"),
            "OMARCHY_KEYMAP_SKIP_RELOAD": "1",
        })
        self.env.start()
        (self.home / ".config/hypr").mkdir(parents=True)
        (self.home / ".config/omarchy").mkdir(parents=True)
        (self.home / "omarchy/config/omarchy").mkdir(parents=True)
        shell = {
            "version": 1,
            "bar": {"layout": {"left": [], "center": [], "right": [{"id": "omarchy.tray"}]}},
            "plugins": [],
        }
        (self.home / "omarchy/config/omarchy/shell.json").write_text(json.dumps(shell))
        (self.home / ".config/hypr/bindings.lua").write_text("-- personal bindings\n")
        (self.home / ".config/omarchy/extensions").mkdir(parents=True)
        (self.home / ".config/omarchy/extensions/omarchy-menu.jsonc").write_text("{\n}\n")

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def record(self, description="Terminal", command="alacritty"):
        return {
            "shortcut": "SUPER + RETURN",
            "description": description,
            "dispatcher": f'hl.dsp.exec_cmd("{command}")',
            "kind": "exec",
            "argument": command,
            "options": {},
            "supported": True,
        }

    def test_normalize_shortcut(self):
        self.assertEqual(keymap.normalize_shortcut("ctrl + super + q"), "SUPER + CTRL + Q")
        with self.assertRaises(ValueError):
            keymap.normalize_shortcut("SUPER")

    def test_friendly_shortcut_resolves_physical_keycode(self):
        self.assertEqual(
            keymap.friendly_shortcut("SUPER + CTRL + code:10", {10: "1"}),
            "SUPER + CTRL + 1",
        )

    def test_conflict_matches_physical_and_displayed_shortcuts(self):
        groups = {
            "source": {"id": "source", "shortcut": "SUPER + CTRL + B"},
            "physical": {"id": "physical", "shortcut": "SUPER + CTRL + code:56"},
        }
        with mock.patch.object(keymap, "keycode_symbols", return_value={56: "B"}):
            conflict = keymap.target_conflict(groups, "source", "SUPER + CTRL + B")
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict["id"], "physical")

    def test_friendly_shortcut_labels_media_keys(self):
        self.assertEqual(
            keymap.friendly_shortcut("ALT + XF86MONBRIGHTNESSDOWN", {}),
            "ALT + BRIGHTNESS DOWN",
        )

    def test_duplicate_action_subtitle_is_hidden(self):
        group = {
            "id": "abc",
            "title": "Brightness down",
            "details": "Brightness down",
            "defaultShortcut": "XF86MONBRIGHTNESSDOWN",
            "shortcut": "XF86MONBRIGHTNESSDOWN",
            "supported": True,
            "overridden": False,
            "disabled": False,
        }
        self.assertEqual(keymap.group_payload(group)["subtitle"], "")

    def test_render_unbinds_before_rebinding(self):
        row = self.record()
        store = {"version": 1, "groups": {"abc": {
            "defaultShortcut": "SUPER + RETURN",
            "target": "SUPER + T",
            "bindings": [row],
        }}}
        output = keymap.render_generated(store)
        self.assertIn('hl.unbind("SUPER + RETURN")', output)
        self.assertIn('hl.unbind("SUPER + T")', output)
        self.assertIn('o.bind("SUPER + T", "Terminal", "alacritty")', output)
        self.assertLess(output.index("hl.unbind"), output.index("o.bind"))

    def test_generated_keymap_defines_safe_capture_submap(self):
        output = keymap.render_generated({"version": 1, "groups": {}})
        self.assertIn('hl.define_submap("omarchy-keymap-capture"', output)
        self.assertIn('hl.bind("SUPER + ESCAPE", hl.dsp.submap("reset")', output)

    def test_disabled_binding_is_only_unbound(self):
        store = {"version": 1, "groups": {"abc": {
            "defaultShortcut": "SUPER + RETURN",
            "target": None,
            "bindings": [self.record()],
        }}}
        output = keymap.render_generated(store)
        self.assertIn('hl.unbind("SUPER + RETURN")', output)
        self.assertNotIn("o.bind(", output)

    def test_bar_presence_keeps_panel_enabled(self):
        keymap.set_bar_presence(False)
        config = json.loads(keymap.paths()["shell"].read_text())
        self.assertFalse(keymap.bar_visible(config))
        self.assertIn({"id": keymap.PLUGIN_ID}, config["plugins"])
        keymap.set_bar_presence(True)
        config = json.loads(keymap.paths()["shell"].read_text())
        self.assertTrue(keymap.bar_visible(config))
        self.assertNotIn({"id": keymap.PLUGIN_ID}, config["plugins"])

    def test_hook_is_idempotent(self):
        original = "-- custom\n"
        once = keymap.ensure_hook(original)
        twice = keymap.ensure_hook(once)
        self.assertEqual(once, twice)
        self.assertEqual(once.count(keymap.HOOK_START), 1)

    def test_special_input_bindings_are_read_only(self):
        records = [self.record()]
        records[0]["shortcut"] = "SUPER + mouse:272"
        with mock.patch.object(keymap, "scan_bindings", return_value=records):
            group = next(iter(keymap.baseline_groups().values()))
        self.assertFalse(group["supported"])

    def test_install_and_uninstall_are_symmetric(self):
        with redirect_stdout(StringIO()):
            self.assertEqual(keymap.cmd_install(SimpleNamespace(with_bar=False)), 0)
        bindings = keymap.paths()["bindings"].read_text()
        menu = keymap.paths()["menu"].read_text()
        shell = json.loads(keymap.paths()["shell"].read_text())
        self.assertIn(keymap.HOOK_START, bindings)
        self.assertIn(keymap.MENU_START, menu)
        self.assertIn({"id": keymap.PLUGIN_ID}, shell["plugins"])

        with redirect_stdout(StringIO()):
            self.assertEqual(keymap.cmd_uninstall(SimpleNamespace(purge=True)), 0)
        self.assertNotIn(keymap.HOOK_START, keymap.paths()["bindings"].read_text())
        self.assertNotIn(keymap.MENU_START, keymap.paths()["menu"].read_text())
        self.assertFalse(keymap.paths()["generated"].exists())


if __name__ == "__main__":
    unittest.main()
