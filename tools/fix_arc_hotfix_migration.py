from pathlib import Path

path = Path(__file__).with_name("apply_arc_classroom_hotfix.py")
text = path.read_text(encoding="utf-8")
replacements = {
    "'''            .gridColumnAlignment(.leading)\n": "'''                .gridColumnAlignment(.leading)\n",
    "\n            .frame(maxWidth: .infinity)\n": "\n                .frame(maxWidth: .infinity)\n",
    "\n\n            if !model.legacyLLMKey.isEmpty {\n": "\n\n                if !model.legacyLLMKey.isEmpty {\n",
    "\n\n            GroupBox(\"Virginia Tech ARC quick setup\") {\n": "\n\n                GroupBox(\"Virginia Tech ARC quick setup\") {\n",
}
for old, new in replacements.items():
    if old not in text:
        raise RuntimeError(f"migration marker not found: {old!r}")
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
