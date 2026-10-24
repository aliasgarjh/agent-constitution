"""python -m agent_constitution validate path/to/constitution.yaml"""
import sys

from .constitution import Constitution, ConstitutionError


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "validate":
        print("usage: python -m agent_constitution validate <constitution.yaml>")
        return 2
    try:
        c = Constitution.from_yaml(argv[2])
    except (ConstitutionError, ValueError, KeyError) as e:
        print(f"INVALID: {e}")
        return 1
    print(f"OK: {len(c.constraints)} constraints, {len(c.decision_rights)} decision classes, "
          f"{len(c.sources)} source policies, {len(c.breakers)} breakers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
