#!/usr/bin/env python3
"""Safe backend for the Omarchy Keyboard Shortcuts plugin."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any


PLUGIN_ID = "io.github.sahzudin.keymap"
VERSION = 1
HOOK_START = "-- omarchy-keymap:start"
HOOK_END = "-- omarchy-keymap:end"
MENU_START = "  // omarchy-keymap:start"
MENU_END = "  // omarchy-keymap:end"
MODIFIER_ORDER = ("SUPER", "SHIFT", "CTRL", "ALT")
MODIFIERS = {"SUPER", "SHIFT", "CTRL", "CONTROL", "ALT"}
KEYSYM_LABELS = {
    "minus": "MINUS",
    "equal": "EQUAL",
    "comma": "COMMA",
    "period": "PERIOD",
    "slash": "SLASH",
    "backslash": "BACKSLASH",
    "bracketleft": "BRACKETLEFT",
    "bracketright": "BRACKETRIGHT",
    "semicolon": "SEMICOLON",
    "apostrophe": "APOSTROPHE",
    "grave": "GRAVE",
    "space": "SPACE",
    "return": "RETURN",
    "escape": "ESCAPE",
    "tab": "TAB",
    "backspace": "BACKSPACE",
    "xf86monbrightnessup": "BRIGHTNESS UP",
    "xf86monbrightnessdown": "BRIGHTNESS DOWN",
    "xf86kbdbrightnessup": "KEYBOARD BRIGHTNESS UP",
    "xf86kbdbrightnessdown": "KEYBOARD BRIGHTNESS DOWN",
    "xf86kbdlightonoff": "KEYBOARD BACKLIGHT",
    "xf86audioraisevolume": "VOLUME UP",
    "xf86audiolowervolume": "VOLUME DOWN",
    "xf86audiomute": "VOLUME MUTE",
    "xf86audiomicmute": "MICROPHONE MUTE",
    "xf86audionext": "NEXT TRACK",
    "xf86audioprev": "PREVIOUS TRACK",
    "xf86audioplay": "PLAY",
    "xf86audiopause": "PAUSE",
    "xf86audiostop": "STOP",
    "xf86calculator": "CALCULATOR",
    "xf86poweroff": "POWER",
    "xf86touchpadtoggle": "TOUCHPAD TOGGLE",
    "xf86touchpadon": "TOUCHPAD ON",
    "xf86touchpadoff": "TOUCHPAD OFF",
}


def home_path() -> Path:
    return Path(os.environ.get("OMARCHY_KEYMAP_HOME", Path.home())).expanduser()


def omarchy_path() -> Path:
    return Path(os.environ.get("OMARCHY_KEYMAP_OMARCHY_PATH", "/usr/share/omarchy"))


def plugin_path() -> Path:
    return Path(__file__).resolve().parent.parent


def paths() -> dict[str, Path]:
    home = home_path()
    return {
        "hyprland": home / ".config/hypr/hyprland.lua",
        "bindings": home / ".config/hypr/bindings.lua",
        "generated": home / ".config/hypr/keymap.lua",
        "data": home / ".config/omarchy-keymap/overrides.json",
        "lock": home / ".local/state/omarchy-keymap/lock",
        "backups": home / ".local/state/omarchy-keymap/backups",
        "menu": home / ".config/omarchy/extensions/omarchy-menu.jsonc",
        "shell": home / ".config/omarchy/shell.json",
        "shell_defaults": omarchy_path() / "config/omarchy/shell.json",
    }


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if payload.get("ok", False) else 1


@contextlib.contextmanager
def locked():
    lock_path = paths()["lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_dir = paths()["backups"]
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = backup_dir / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, target)
    return target


def atomic_write(path: Path, content: str, *, make_backup: bool = True) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = backup(path) if make_backup else None
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    return saved


def restore_file(path: Path, content: str | None) -> None:
    if content is None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    else:
        atomic_write(path, content, make_backup=False)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def normalize_shortcut(value: str) -> str:
    modifiers: set[str] = set()
    key = ""
    for raw in value.split("+"):
        token = raw.strip()
        upper = token.upper()
        if upper in MODIFIERS:
            modifiers.add("CTRL" if upper == "CONTROL" else upper)
        elif token:
            if key:
                raise ValueError("a shortcut must contain exactly one non-modifier key")
            key = token
    if not key:
        raise ValueError("a shortcut needs a non-modifier key")
    if len(key) == 1:
        key = key.upper()
    elif not key.startswith(("code:", "mouse:", "switch:")):
        key = key.upper()
    return " + ".join([name for name in MODIFIER_ORDER if name in modifiers] + [key])


def display_keysym(symbol: str) -> str:
    if len(symbol) == 1:
        return symbol.upper()
    return KEYSYM_LABELS.get(symbol.casefold(), symbol)


@lru_cache(maxsize=1)
def keycode_symbols() -> dict[int, str]:
    # XKB keycodes are physical-key identifiers. Resolve them through the
    # currently compiled keymap for presentation, while keeping code:N in all
    # persisted data so the binding remains layout-independent.
    symbols: dict[int, str] = {
        **{code: str(code - 9) for code in range(10, 19)},
        19: "0",
        20: "MINUS",
        21: "EQUAL",
        34: "BRACKETLEFT",
        35: "BRACKETRIGHT",
        59: "COMMA",
        60: "PERIOD",
        61: "SLASH",
    }
    try:
        result = subprocess.run(
            ["xkbcli", "compile-keymap"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return symbols
    if result.returncode:
        return symbols

    codes_by_name = {
        name: int(code)
        for name, code in re.findall(r"<([A-Za-z0-9_]+)>\s*=\s*([0-9]+)\s*;", result.stdout)
    }
    for name, symbol in re.findall(
        r"key\s*<([A-Za-z0-9_]+)>\s*\{\s*\[\s*([^,\s\]]+)", result.stdout
    ):
        code = codes_by_name.get(name)
        if code is not None and symbol != "NoSymbol":
            symbols[code] = display_keysym(symbol)
    return symbols


def friendly_shortcut(value: str, symbols: dict[int, str] | None = None) -> str:
    if not value:
        return ""
    resolved = keycode_symbols() if symbols is None else symbols

    def replace(match: re.Match[str]) -> str:
        code = int(match.group(1))
        return resolved.get(code, f"KEYCODE {code}")

    physical_resolved = re.sub(r"code:([0-9]+)", replace, value, flags=re.I)
    parts = [part.strip() for part in physical_resolved.split(" + ")]
    if parts:
        parts[-1] = display_keysym(parts[-1])
    return " + ".join(parts)


def load_store() -> dict[str, Any]:
    path = paths()["data"]
    if not path.exists():
        return {"version": VERSION, "groups": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read {path}: {error}") from error
    if not isinstance(value, dict) or value.get("version") != VERSION:
        raise RuntimeError(f"Unsupported keymap data in {path}")
    if not isinstance(value.get("groups"), dict):
        value["groups"] = {}
    return value


def save_store(store: dict[str, Any]) -> None:
    content = json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write(paths()["data"], content)


def scan_bindings() -> list[dict[str, Any]]:
    config = paths()["hyprland"]
    if not config.exists():
        raise RuntimeError(f"Missing Hyprland configuration: {config}")
    env = os.environ.copy()
    env["HOME"] = str(home_path())
    env["OMARCHY_PATH"] = str(omarchy_path())
    env["OMARCHY_KEYMAP_SCAN"] = "1"
    result = subprocess.run(
        ["lua", str(plugin_path() / "scripts/scan.lua"), str(config)],
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Binding discovery failed")
    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Binding discovery returned invalid JSON: {error}") from error
    if not isinstance(records, list):
        raise RuntimeError("Binding discovery did not return a list")
    return records


def binding_fingerprint(shortcut: str, records: list[dict[str, Any]]) -> str:
    stable = [
        {
            "description": row.get("description"),
            "dispatcher": row.get("dispatcher", ""),
            "kind": row.get("kind", ""),
            "argument": row.get("argument", ""),
            "options": row.get("options", {}),
        }
        for row in records
    ]
    raw = shortcut + "\0" + json.dumps(stable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def baseline_groups() -> dict[str, dict[str, Any]]:
    by_shortcut: dict[str, list[dict[str, Any]]] = {}
    for record in scan_bindings():
        shortcut = normalize_shortcut(str(record.get("shortcut", "")))
        record["shortcut"] = shortcut
        by_shortcut.setdefault(shortcut, []).append(record)

    groups: dict[str, dict[str, Any]] = {}
    for shortcut, records in by_shortcut.items():
        identifier = binding_fingerprint(shortcut, records)
        special_input = bool(re.search(r"(^|\+\s*)(mouse:|mouse_|switch:)", shortcut, re.I)) \
            or any(bool((record.get("options") or {}).get("mouse")) if isinstance(record.get("options"), dict) else False for record in records)
        descriptions: list[str] = []
        for record in records:
            description = str(record.get("description") or "").strip()
            if description and description not in descriptions:
                descriptions.append(description)
        title = descriptions[0] if descriptions else "Unnamed binding"
        if len(descriptions) > 1:
            title += f" (+{len(descriptions) - 1} related)"
        groups[identifier] = {
            "id": identifier,
            "defaultShortcut": shortcut,
            "title": title,
            "descriptions": descriptions,
            "bindings": records,
            "supported": all(bool(record.get("supported")) for record in records) and not special_input,
        }
    return groups


def effective_groups() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    baseline = baseline_groups()
    store = load_store()
    groups = dict(baseline)
    for identifier, override in store["groups"].items():
        if identifier not in groups and isinstance(override, dict):
            records = override.get("bindings") or []
            descriptions = [str(row.get("description")) for row in records if row.get("description")]
            groups[identifier] = {
                "id": identifier,
                "defaultShortcut": override.get("defaultShortcut", ""),
                "title": descriptions[0] if descriptions else "Removed binding",
                "descriptions": descriptions,
                "bindings": records,
                "supported": all(bool(row.get("supported")) for row in records),
                "stale": True,
            }

    for identifier, group in groups.items():
        override = store["groups"].get(identifier)
        group["shortcut"] = override.get("target") if override else group["defaultShortcut"]
        group["overridden"] = override is not None
        group["disabled"] = override is not None and override.get("target") is None
        group["details"] = " • ".join(group["descriptions"])
    return groups, store


def lua_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def lua_value(value: Any) -> str:
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return lua_string(value)
    if isinstance(value, list):
        return "{ " + ", ".join(lua_value(item) for item in value) + " }"
    if isinstance(value, dict):
        parts = []
        for key in sorted(value):
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                parts.append(f"{key} = {lua_value(value[key])}")
            else:
                parts.append(f"[{lua_string(str(key))}] = {lua_value(value[key])}")
        return "{ " + ", ".join(parts) + " }"
    raise ValueError(f"Cannot render {type(value).__name__} as Lua")


def render_generated(store: dict[str, Any]) -> str:
    overrides = [value for value in store["groups"].values() if isinstance(value, dict)]
    chords: set[str] = set()
    for override in overrides:
        default = override.get("defaultShortcut")
        target = override.get("target")
        if default:
            chords.add(normalize_shortcut(default))
        if target:
            chords.add(normalize_shortcut(target))

    lines = [
        "-- Generated by Omarchy Keyboard Shortcuts. Do not edit by hand.",
        "-- Use the settings panel; handwritten bindings belong in bindings.lua.",
        'if os.getenv("OMARCHY_KEYMAP_SCAN") == "1" then return end',
        "",
        'hl.define_submap("omarchy-keymap-capture", function()',
        '  hl.bind("SUPER + ESCAPE", hl.dsp.submap("reset"), { description = "Exit keyboard shortcut capture" })',
        "end)",
        "",
    ]
    for chord in sorted(chords):
        lines.append(f"hl.unbind({lua_string(chord)})")
    if chords:
        lines.append("")

    for override in sorted(overrides, key=lambda value: str(value.get("target") or "")):
        target = override.get("target")
        if not target:
            continue
        target = normalize_shortcut(target)
        for record in override.get("bindings", []):
            if not record.get("supported"):
                raise ValueError("An unsupported Lua callback cannot be written as an override")
            description = record.get("description")
            if record.get("kind") == "exec":
                dispatcher = lua_string(str(record.get("argument", "")))
            else:
                dispatcher = str(record.get("dispatcher", ""))
                if not re.match(r"^hl\.dsp\.[A-Za-z0-9_.]+\(.*\)$", dispatcher, re.S):
                    raise ValueError("Refusing to write an unsafe dispatcher expression")
            options = record.get("options") or {}
            arguments = [lua_string(target), lua_value(description), dispatcher]
            if options:
                arguments.append(lua_value(options))
            lines.append("o.bind(" + ", ".join(arguments) + ")")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def validate_lua(path: Path) -> None:
    result = subprocess.run(
        ["luac", "-p", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Generated Lua did not compile")


def reload_hyprland() -> None:
    if os.environ.get("OMARCHY_KEYMAP_SKIP_RELOAD") == "1":
        return
    reload_result = subprocess.run(
        ["hyprctl", "reload"], capture_output=True, text=True, timeout=20
    )
    if reload_result.returncode:
        raise RuntimeError(reload_result.stderr.strip() or reload_result.stdout.strip() or "hyprctl reload failed")
    errors = subprocess.run(
        ["hyprctl", "configerrors"], capture_output=True, text=True, timeout=20
    )
    output = (errors.stdout + errors.stderr).strip()
    if errors.returncode or (output and output.lower() not in {"no errors", "ok"}):
        raise RuntimeError(output or "Hyprland reported configuration errors")


def apply_store(store: dict[str, Any]) -> None:
    generated = paths()["generated"]
    previous = read_text(generated)
    content = render_generated(store)
    atomic_write(generated, content)
    try:
        validate_lua(generated)
        reload_hyprland()
    except Exception:
        restore_file(generated, previous)
        with contextlib.suppress(Exception):
            reload_hyprland()
        raise


def group_payload(group: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: group.get(key)
        for key in (
            "id", "title", "details", "defaultShortcut", "shortcut", "supported",
            "overridden", "disabled", "stale",
        )
        if key in group
    }
    payload["displayShortcut"] = friendly_shortcut(str(group.get("shortcut") or ""))
    payload["displayDefaultShortcut"] = friendly_shortcut(str(group.get("defaultShortcut") or ""))
    if not group.get("supported"):
        payload["subtitle"] = "Advanced Lua or device binding · read-only"
    elif group.get("overridden"):
        payload["subtitle"] = f"Default: {payload['displayDefaultShortcut']}"
    else:
        details = str(group.get("details") or "")
        payload["subtitle"] = "" if details.casefold() == str(group.get("title") or "").casefold() else details
    return payload


def load_shell_config() -> dict[str, Any]:
    path = paths()["shell"]
    source = path if path.exists() else paths()["shell_defaults"]
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read shell configuration: {error}") from error
    if not isinstance(value, dict):
        value = {}
    value["version"] = 1
    bar = value.setdefault("bar", {})
    layout = bar.setdefault("layout", {})
    for section in ("left", "center", "right"):
        if not isinstance(layout.get(section), list):
            layout[section] = []
    if not isinstance(value.get("plugins"), list):
        value["plugins"] = []
    return value


def entry_id(entry: Any) -> str:
    return str(entry.get("id", "")) if isinstance(entry, dict) else str(entry)


def bar_visible(config: dict[str, Any]) -> bool:
    layout = config.get("bar", {}).get("layout", {})
    return any(entry_id(entry) == PLUGIN_ID for section in layout.values() if isinstance(section, list) for entry in section)


def refresh_shell() -> None:
    if os.environ.get("OMARCHY_KEYMAP_SKIP_RELOAD") == "1":
        return
    subprocess.run(
        ["omarchy-shell", "shell", "reloadConfig"],
        capture_output=True,
        text=True,
        timeout=10,
    )


def set_bar_presence(visible: bool) -> None:
    config = load_shell_config()
    layout = config["bar"]["layout"]
    for section in ("left", "center", "right"):
        layout[section] = [entry for entry in layout[section] if entry_id(entry) != PLUGIN_ID]
    config["plugins"] = [entry for entry in config["plugins"] if entry_id(entry) != PLUGIN_ID]
    if visible:
        target = layout["right"]
        tray_index = next((index for index, entry in enumerate(target) if entry_id(entry) == "omarchy.tray"), -1)
        target.insert(tray_index + 1 if tray_index >= 0 else len(target), {"id": PLUGIN_ID})
    else:
        config["plugins"].append({"id": PLUGIN_ID})
    atomic_write(paths()["shell"], json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    refresh_shell()


def ensure_hook(content: str) -> str:
    if HOOK_START in content and HOOK_END in content:
        return content
    block = f'\n{HOOK_START}\nrequire("hypr.keymap")\n{HOOK_END}\n'
    return content.rstrip() + "\n" + block


def remove_marked(content: str, start: str, end: str) -> str:
    pattern = re.compile(rf"\n?{re.escape(start)}.*?{re.escape(end)}\n?", re.S)
    return pattern.sub("\n", content).rstrip() + "\n"


def strip_jsonc(content: str) -> str:
    out: list[str] = []
    index = 0
    in_string = False
    while index < len(content):
        character = content[index]
        if in_string:
            out.append(character)
            if character == "\\" and index + 1 < len(content):
                out.append(content[index + 1])
                index += 2
                continue
            if character == '"':
                in_string = False
            index += 1
        elif character == '"':
            in_string = True
            out.append(character)
            index += 1
        elif content.startswith("//", index):
            index = content.find("\n", index)
            if index < 0:
                break
        elif content.startswith("/*", index):
            finish = content.find("*/", index + 2)
            index = len(content) if finish < 0 else finish + 2
        else:
            out.append(character)
            index += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def add_menu_entry() -> None:
    path = paths()["menu"]
    content = read_text(path) or "{\n}\n"
    if MENU_START in content:
        return
    try:
        parsed = json.loads(strip_jsonc(content))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Could not update invalid JSONC in {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Menu configuration in {path} is not an object")
    entries: list[tuple[str, dict[str, str]]] = []
    if "setup.keyboard" not in parsed:
        entries.append(("setup.keyboard", {"icon": "", "label": "Keyboard"}))
    entries.append(("setup.keyboard.shortcuts", {
        "icon": "󰌌",
        "label": "Keyboard Shortcuts",
        "description": "View and change Omarchy keyboard shortcuts",
        "action": f"omarchy-shell shell summon {PLUGIN_ID} '{{}}'",
    }))
    brace = content.find("{")
    if brace < 0:
        raise RuntimeError(f"Menu configuration in {path} has no root object")
    body = [MENU_START]
    for key, value in entries:
        body.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},")
    body.append(MENU_END)
    insertion = "\n".join(body) + "\n"
    atomic_write(path, content[: brace + 1] + "\n" + insertion + content[brace + 1 :])


def remove_menu_entry() -> None:
    path = paths()["menu"]
    content = read_text(path)
    if content and MENU_START in content:
        atomic_write(path, remove_marked(content, MENU_START, MENU_END))


def cmd_list(_: argparse.Namespace) -> int:
    groups, _ = effective_groups()
    ordered = sorted(groups.values(), key=lambda group: (group["title"].casefold(), group["defaultShortcut"]))
    config = load_shell_config()
    return emit({
        "ok": True,
        "bindings": [group_payload(group) for group in ordered],
        "barVisible": bar_visible(config),
        "generatedFile": str(paths()["generated"]),
    })


def shortcut_collision_key(value: str) -> str:
    """Normalize both symbolic and physical shortcuts as the user sees them."""
    return normalize_shortcut(friendly_shortcut(normalize_shortcut(value)))


def target_conflict(groups: dict[str, dict[str, Any]], identifier: str, target: str) -> dict[str, Any] | None:
    wanted = shortcut_collision_key(target)
    for other_id, other in groups.items():
        shortcut = other.get("shortcut")
        if other_id != identifier and shortcut and shortcut_collision_key(str(shortcut)) == wanted:
            return other
    return None


def make_override(group: dict[str, Any], target: str | None) -> dict[str, Any]:
    return {
        "defaultShortcut": group["defaultShortcut"],
        "target": target,
        "bindings": group["bindings"],
    }


def cmd_set(args: argparse.Namespace) -> int:
    with locked():
        groups, store = effective_groups()
        group = groups.get(args.id)
        if not group:
            return emit({"ok": False, "error": "Shortcut no longer exists; refresh the panel."})
        if not group.get("supported"):
            return emit({"ok": False, "error": "This shortcut uses a Lua callback and is read-only."})
        try:
            target = normalize_shortcut(args.shortcut)
        except ValueError as error:
            return emit({"ok": False, "error": str(error)})
        conflict = target_conflict(groups, args.id, target)
        if conflict and not args.replace:
            return emit({
                "ok": False,
                "conflict": group_payload(conflict),
                "error": f"{friendly_shortcut(target)} is currently assigned to {conflict['title']}.",
            })
        if conflict:
            store["groups"][conflict["id"]] = make_override(conflict, None)
        if target == group["defaultShortcut"]:
            store["groups"].pop(args.id, None)
        else:
            store["groups"][args.id] = make_override(group, target)
        previous = read_text(paths()["data"])
        save_store(store)
        try:
            apply_store(store)
        except Exception as error:
            restore_file(paths()["data"], previous)
            return emit({"ok": False, "error": f"Could not apply shortcut; changes were rolled back: {error}"})
    return emit({"ok": True, "shortcut": target})


def cmd_disable(args: argparse.Namespace) -> int:
    with locked():
        groups, store = effective_groups()
        group = groups.get(args.id)
        if not group:
            return emit({"ok": False, "error": "Shortcut no longer exists; refresh the panel."})
        store["groups"][args.id] = make_override(group, None)
        previous = read_text(paths()["data"])
        save_store(store)
        try:
            apply_store(store)
        except Exception as error:
            restore_file(paths()["data"], previous)
            return emit({"ok": False, "error": f"Could not disable shortcut; changes were rolled back: {error}"})
    return emit({"ok": True})


def cmd_reset(args: argparse.Namespace) -> int:
    with locked():
        groups, store = effective_groups()
        group = groups.get(args.id)
        if not group:
            return emit({"ok": False, "error": "Shortcut no longer exists; refresh the panel."})
        conflict = target_conflict(groups, args.id, group["defaultShortcut"])
        if conflict:
            return emit({
                "ok": False,
                "error": f"Restore {conflict['title']} first; it currently uses {friendly_shortcut(group['defaultShortcut'])}.",
            })
        previous = read_text(paths()["data"])
        store["groups"].pop(args.id, None)
        save_store(store)
        try:
            apply_store(store)
        except Exception as error:
            restore_file(paths()["data"], previous)
            return emit({"ok": False, "error": f"Could not restore shortcut; changes were rolled back: {error}"})
    return emit({"ok": True})


def cmd_reset_all(_: argparse.Namespace) -> int:
    with locked():
        store = {"version": VERSION, "groups": {}}
        previous = read_text(paths()["data"])
        save_store(store)
        try:
            apply_store(store)
        except Exception as error:
            restore_file(paths()["data"], previous)
            return emit({"ok": False, "error": f"Could not restore defaults; changes were rolled back: {error}"})
    return emit({"ok": True})


def cmd_set_bar(args: argparse.Namespace) -> int:
    try:
        set_bar_presence(args.visible == "true")
        return emit({"ok": True, "barVisible": args.visible == "true"})
    except Exception as error:
        return emit({"ok": False, "error": str(error)})


def cmd_install(args: argparse.Namespace) -> int:
    with locked():
        bindings = paths()["bindings"]
        previous_bindings = read_text(bindings)
        previous_generated = read_text(paths()["generated"])
        if previous_bindings is None:
            return emit({"ok": False, "error": f"Missing {bindings}; run 'omarchy refresh hyprland' first."})
        try:
            atomic_write(bindings, ensure_hook(previous_bindings))
            store = load_store()
            apply_store(store)
        except Exception as error:
            restore_file(bindings, previous_bindings)
            restore_file(paths()["generated"], previous_generated)
            with contextlib.suppress(Exception):
                reload_hyprland()
            return emit({"ok": False, "error": f"Installation failed and was rolled back: {error}"})
        try:
            add_menu_entry()
            set_bar_presence(args.with_bar)
        except Exception as error:
            return emit({"ok": False, "error": f"Keyboard support installed, but shell integration failed: {error}"})
    return emit({"ok": True, "barVisible": args.with_bar})


def cmd_uninstall(args: argparse.Namespace) -> int:
    with locked():
        bindings = paths()["bindings"]
        content = read_text(bindings)
        if content and HOOK_START in content:
            previous = content
            atomic_write(bindings, remove_marked(content, HOOK_START, HOOK_END))
            try:
                reload_hyprland()
            except Exception as error:
                restore_file(bindings, previous)
                with contextlib.suppress(Exception):
                    reload_hyprland()
                return emit({"ok": False, "error": f"Uninstall failed and was rolled back: {error}"})
        remove_menu_entry()
        config = load_shell_config()
        layout = config["bar"]["layout"]
        for section in ("left", "center", "right"):
            layout[section] = [entry for entry in layout[section] if entry_id(entry) != PLUGIN_ID]
        config["plugins"] = [entry for entry in config["plugins"] if entry_id(entry) != PLUGIN_ID]
        atomic_write(paths()["shell"], json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        refresh_shell()
        if args.purge:
            for path in (paths()["generated"], paths()["data"]):
                if path.exists():
                    backup(path)
                    path.unlink()
    return emit({"ok": True, "purged": args.purge})


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list").set_defaults(handler=cmd_list)
    set_parser = commands.add_parser("set")
    set_parser.add_argument("id")
    set_parser.add_argument("shortcut")
    set_parser.add_argument("--replace", action="store_true")
    set_parser.set_defaults(handler=cmd_set)
    disable_parser = commands.add_parser("disable")
    disable_parser.add_argument("id")
    disable_parser.set_defaults(handler=cmd_disable)
    reset_parser = commands.add_parser("reset")
    reset_parser.add_argument("id")
    reset_parser.set_defaults(handler=cmd_reset)
    commands.add_parser("reset-all").set_defaults(handler=cmd_reset_all)
    bar_parser = commands.add_parser("set-bar")
    bar_parser.add_argument("visible", choices=("true", "false"))
    bar_parser.set_defaults(handler=cmd_set_bar)
    install_parser = commands.add_parser("install")
    install_parser.add_argument("--with-bar", action="store_true")
    install_parser.set_defaults(handler=cmd_install)
    uninstall_parser = commands.add_parser("uninstall")
    uninstall_parser.add_argument("--purge", action="store_true")
    uninstall_parser.set_defaults(handler=cmd_uninstall)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except Exception as error:
        return emit({"ok": False, "error": str(error)})


if __name__ == "__main__":
    sys.exit(main())
