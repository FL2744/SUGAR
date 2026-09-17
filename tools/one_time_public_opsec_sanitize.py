from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
WORKFLOW = ROOT / ".github" / "workflows" / "one-time-public-opsec-sanitize.yml"

# Real mission/case material does not belong in the public engine repository.
REMOVE = [
    ROOT / "examples" / "cases" / "kyrgyzstan_2026",
    ROOT / "examples" / "example-map.html",
    ROOT / "tests" / "test_kyrgyzstan_case_data.py",
    ROOT / "tests" / "test_kyrgyzstan_location_enrichment.py",
    ROOT / "tests" / "test_kyrgyzstan_assessment_calibration.py",
]

for path in REMOVE:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

TEXT_EXTENSIONS = {
    ".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".swift",
    ".ps1", ".sh", ".json", ".html", ".plist", ".ini", ".cfg",
}

# Semantic/API renames first. These deliberately make the analytic model target-neutral,
# rather than merely hiding country names in prose.
REPLACEMENTS = [
    ("confirmed_prc_support_verified", "confirmed_sponsor_support_verified"),
    ("probable_prc_support_verified", "probable_sponsor_support_verified"),
    ("official_prc_support", "official_sponsor_support"),
    ("official_prc_source", "official_sponsor_source"),
    ("china_russia_joint_activity", "cross_state_joint_activity"),
    ("prc_support", "sponsor_support"),
    ("PRC_SUPPORT", "SPONSOR_SUPPORT"),
    ("PRC-support", "sponsor-support"),
    ("PRC support", "sponsor support"),
    ("PRC-linked", "sponsor-linked"),
    ("PRC linked", "sponsor linked"),
    ("PRC-supported", "state-supported"),
    ("PRC supported", "state-supported"),
    ("PRC government-supported", "state-supported"),
    ("PRC government support", "state or sponsor support"),
    ("PRC state entities", "sponsoring-state entities"),
    ("PRC state entity", "sponsoring-state entity"),
    ("PRC activities", "sponsor-linked activities"),
    ("PRC activity", "sponsor-linked activity"),
    ("PRC networks", "sponsor-linked networks"),
    ("PRC network", "sponsor-linked network"),
    ("PRC sources", "sponsor sources"),
    ("PRC source", "sponsor source"),
    ("PRC Cultural Influence Network Research Update", "State-Supported Public Engagement Research Update"),
    ("PRC Cultural Influence Network", "State-Supported Public Engagement"),
    ("China-Russia joint activity", "cross-state joint activity"),
    ("China-Russia", "cross-state"),
    ("China influence score", "single influence score"),
    ("China-influence score", "single influence score"),
    ("Chinese social-media sources", "platform-specific social-media sources"),
    ("Chinese social media sources", "platform-specific social-media sources"),
    ("Simplified Chinese, Russian", "Spanish, Russian"),
    ('"English", "Chinese", "Local language"', '"English", "Spanish", "Local language"'),
    ("Chinese identity, language, branding, or location", "national identity, language, branding, or location"),
    ("Chinese identity, language, or location", "national identity, language, or location"),
    ("Chinese language, branding, or location", "national language, branding, or location"),
    ("Chinese-language", "foreign-language"),
    ("mainland China", "the sponsoring state's home territory"),
    ("promotion of China", "promotion of a sponsoring state"),
    ("official PRC reporting", "official sponsor reporting"),
    ("Official PRC reporting", "Official sponsor reporting"),
    ("official PRC source", "official sponsor source"),
    ("Official PRC source", "Official sponsor source"),
    ("孔子学院", "文化交流"),
    ("鲁班工坊", "技术培训"),
    ("中国共产党", "某国执政党"),
    ("习近平", "某国领导人"),
    ("中国", "国际"),
    ("北京", "首都"),
]

# Exact public-facing prose improvements for known high-visibility surfaces.
SPECIAL = {
    "SUGAR is a cross-platform public-source research system for collecting social-media material, preserving provenance, organizing evidence, conducting spatial and structured analysis, and producing reviewable research products. It is developed for Virginia Tech Diplomacy Lab work on public diplomacy and PRC-supported cultural/public-engagement networks, while the core remains platform-neutral.":
    "SUGAR is a cross-platform public-source research system for collecting social-media material, preserving provenance, organizing evidence, conducting spatial and structured analysis, and producing reviewable research products. The public engine is target-neutral; project-specific targets, query plans, and case data belong in non-public project configuration.",
    '  --description "PRC public-diplomacy research"': '  --description "public-diplomacy research"',
    '    description="PRC public-diplomacy research",': '    description="public-diplomacy research",',
    'sugar-project init ./team4 --name "Diplomacy Lab Team 4" --description "PRC public-diplomacy research"':
    'sugar-project init ./research --name "Public Diplomacy Research" --description "public-diplomacy research"',
    'self.state_title = QLineEdit("PRC Cultural Influence Network Research Update")':
    'self.state_title = QLineEdit("State-Supported Public Engagement Research Update")',
    'title = str(config.get("title") or "PRC Cultural Influence Network Research Update").strip()':
    'title = str(config.get("title") or "State-Supported Public Engagement Research Update").strip()',
    'package.add_argument("--title", default="PRC Cultural Influence Network Research Update")':
    'package.add_argument("--title", default="State-Supported Public Engagement Research Update")',
    'title: str = "PRC Cultural Influence Network Research Update"':
    'title: str = "State-Supported Public Engagement Research Update"',
    '"Triage overt, public PRC government-supported cultural, educational, technical, commercial, "':
    '"Triage overt, public state-supported cultural, educational, technical, commercial, "',
    '"or public-diplomacy activity outside mainland China. Relevant examples can include Confucius "':
    '"or public-diplomacy activity involving a sponsoring state outside its home territory. Relevant examples can include language-and-culture "',
    '"Institutes, Luban Workshops, Chinese cultural centers, embassy/consulate public engagement, "':
    '"centers, technical training programs, cultural centers, embassy/consulate public engagement, "',
    '"explicit China-Russia or third-country joint activity, and explicit overlap with U.S. public-"':
    '"explicit cross-state or third-country joint activity, and explicit overlap with U.S. public-"',
    '"diplomacy efforts. Ordinary discussion about China is not automatically relevant."':
    '"diplomacy efforts. Ordinary discussion about a country is not automatically relevant."',
    "The repository includes an opt-in live smoke test using the public 2026-07-13 Weibo status `5320265912291527`, a post about ANTA KAI 3 that explicitly discusses blending Chinese kite imagery with other cultural motifs.":
    "The repository includes an opt-in bounded live smoke test using a stable public status observed during development.",
    "# The text discusses ANTA KAI 3's blending of Chinese kite imagery and other cultural motifs.":
    "# Stable public seed used only to detect changes in the platform's public response surface.",
}

for path in ROOT.rglob("*"):
    if not path.is_file() or ".git" in path.parts or path in {SELF, WORKFLOW}:
        continue
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    original = text
    for old, new in SPECIAL.items():
        text = text.replace(old, new)
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)

    # Remaining target-specific prose: make it generic. Word boundaries avoid platform names.
    text = re.sub(r"\bPRC\b", "sponsoring state", text, flags=re.IGNORECASE)
    text = re.sub(r"\bChina\b", "sponsoring state", text, flags=re.IGNORECASE)
    text = re.sub(r"\bChinese\b", "sponsoring-state", text, flags=re.IGNORECASE)
    text = re.sub(r"\bBeijing\b", "capital city", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCCP\b|\bCPC\b", "ruling party", text, flags=re.IGNORECASE)
    text = re.sub(r"\bConfucius Institutes?\b", "language-and-culture centers", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLuban Workshops?\b", "technical training centers", text, flags=re.IGNORECASE)
    text = re.sub(r"\bXi Jinping\b", "a foreign head of state", text, flags=re.IGNORECASE)
    text = re.sub(r"\bKyrgyzstan\b", "example host country", text, flags=re.IGNORECASE)

    if text != original:
        path.write_text(text, encoding="utf-8")

# Clean up any empty real-case parent directory.
cases = ROOT / "examples" / "cases"
if cases.exists() and not any(cases.iterdir()):
    cases.rmdir()

# Add a durable public-repository boundary document.
policy = ROOT / "docs" / "public-repository-boundaries.md"
policy.write_text(
    "# Public repository boundaries\n\n"
    "SUGAR's public repository contains a target-neutral research engine and generic platform adapters. "
    "Mission-specific targets, country/entity watchlists, operational query plans, real sponsor-focused case data, "
    "and customer-specific analytic prompts should be maintained outside the public repository.\n\n"
    "Platform adapters may document the public or authorized surfaces they support, but should not encode why a "
    "particular project is interested in that platform. Analytic schemas use generic sponsor/state-support concepts "
    "so the same engine can be configured for different research questions without publishing the active target.\n\n"
    "The public-OPSEC regression test scans tracked text for target-specific mission terminology and known real-case "
    "markers. Add project-specific configuration only through external/private project files.\n",
    encoding="utf-8",
)

# Add a regression test without embedding the blocked terms as contiguous literals in the public tree.
test = ROOT / "tests" / "test_public_opsec.py"
test.write_text(
    '''from __future__ import annotations\n\nimport re\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nTEXT_EXTENSIONS = {\n    ".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".swift",\n    ".ps1", ".sh", ".json", ".html", ".plist", ".ini", ".cfg",\n}\n\n\ndef _blocked_terms() -> list[str]:\n    # Split strings keep the guard itself target-neutral to ordinary repository search.\n    return [\n        "P" + "RC",\n        "Chi" + "na",\n        "Chi" + "nese",\n        "Bei" + "jing",\n        "C" + "CP",\n        "C" + "PC",\n        "Con" + "fucius",\n        "Lu" + "ban",\n        "Xi " + "Jinping",\n        "Kyrgyz" + "stan",\n        "孔" + "子学院",\n        "鲁" + "班工坊",\n    ]\n\n\ndef test_public_tree_has_no_target_specific_mission_markers():\n    findings: list[str] = []\n    patterns = [re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])") for term in _blocked_terms()]\n    for path in ROOT.rglob("*"):\n        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_EXTENSIONS:\n            continue\n        try:\n            text = path.read_text(encoding="utf-8")\n        except UnicodeDecodeError:\n            continue\n        for line_no, line in enumerate(text.splitlines(), 1):\n            if any(pattern.search(line) for pattern in patterns):\n                findings.append(f"{path.relative_to(ROOT)}:{line_no}")\n    assert not findings, "Target-specific public-repository markers found: " + ", ".join(findings[:30])\n''',
    encoding="utf-8",
)

print("Public OPSEC sanitization applied.")
