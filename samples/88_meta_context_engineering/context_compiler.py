"""
Context Compiler — assembles the system prompt for the Autonomous Flight Delay Refund System.

This is the mundane part: read files, concatenate, write output.
No AI. No platform. Just file engineering on a filesystem — RAG without the vector database.

Conflict resolution order (highest authority first):
  Layer 1: Framework physics  — DIR-minified.md
  Layer 2: Domain physics     — threat-model > boundaries > standards > intent > acceptance
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

MANIFEST: list[tuple[str, Path]] = [
    ("Framework physics: DIR + ROA + Topology C",   REPO_ROOT / "docs/07-dir-minified/DIR-minified.md"),
    ("Threat Model (highest authority)",             HERE / "3_threat-model.md"),
    ("DIR Boundaries",                               HERE / "2_dir-boundaries.md"),
    ("Coding Standards",                             HERE / "5_coding-standards.md"),
    ("Intent + Data Models",                         HERE / "1_intent.md"),
    ("Acceptance Criteria (Gherkin)",                HERE / "4_acceptance-criteria.md"),
]

SEPARATOR = "=" * 60

def compile_context(output: Path | None = None) -> str:
    sections: list[str] = []
    for label, path in MANIFEST:
        sections.append(f"\n\n{SEPARATOR}\n# CONTEXT: {label}\n# SOURCE:  {path.name}\n{SEPARATOR}\n")
        sections.append(path.read_text(encoding="utf-8"))

    compiled = "".join(sections)

    out = output or HERE / "compiled_system_prompt.txt"
    out.write_text(compiled, encoding="utf-8")
    print(f"Compiled {len(MANIFEST)} files -> {out}  ({compiled.count(chr(10))} lines)")
    return compiled

if __name__ == "__main__":
    compile_context()
