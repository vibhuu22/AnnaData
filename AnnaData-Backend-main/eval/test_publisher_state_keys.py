"""
The publisher and the reader must agree on what a state is called.

Prices are written by local_mandi/feeder.py, running on a machine in India
because the API refuses data centre addresses, and read by Mandi_Price_Tool in
the cloud. The row they meet at is keyed on the state name, and each side
normalises that name with its own copy of the same alias map - "orissa" to
"odisha", "nct of delhi" to "delhi", and four more.

Two copies of one table is the kind of duplication that holds until someone
edits one of them. Add a state to the backend's map and the publisher keeps
writing under the old key: nothing errors, nothing logs, the publisher reports
success, and prices for that state simply stop appearing. The farmer is told
the figures are two months old, which by then they are. This project has met
that shape of failure enough times to put a test under it.

The maps are read out of both files rather than imported, so this needs neither
psycopg nor requests nor a database, and can run anywhere the rest of eval/
runs.

Run: python eval/test_publisher_state_keys.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "AnnaData-Backend-main" / "Mandi_Price_Tool.py"
PUBLISHER = ROOT / "local_mandi" / "feeder.py"


def dict_literal(path: Path, name: str) -> dict:
    """The value of a module-level dict assignment, without importing it."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path.name}")


def main() -> int:
    if not PUBLISHER.exists():
        # The publisher is a separate application and may not be checked out.
        # Absent is not failing; silently passing while it drifts would be.
        print(f"local_mandi/feeder.py is not present - nothing to compare")
        return 0

    backend = dict_literal(BACKEND, "STATE_ALIASES")
    publisher = dict_literal(PUBLISHER, "ALIASES")

    print(f"backend   STATE_ALIASES: {len(backend)} entries")
    print(f"publisher ALIASES:       {len(publisher)} entries")

    if backend == publisher:
        print("\nThe two maps agree. A state normalises to the same key on both sides.")
        return 0

    print("\nFAIL: the maps have drifted. Prices written for any state below")
    print("      would be stored under a key the reader never looks up.\n")
    for alias in sorted(set(backend) | set(publisher)):
        here, there = backend.get(alias), publisher.get(alias)
        if here != there:
            print(f"  {alias!r}: backend -> {here!r}, publisher -> {there!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
