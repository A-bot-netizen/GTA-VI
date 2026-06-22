"""Convenience launcher: python main.py [--dry-run] [--source NAME]

For CI / GitHub Actions, the workflow calls collect.py and report.py directly.
"""
import subprocess
import sys


def main() -> None:
    collect = subprocess.run([sys.executable, "collect.py"] + sys.argv[1:])
    if collect.returncode != 0:
        sys.exit(collect.returncode)
    subprocess.run([sys.executable, "report.py"], check=True)


if __name__ == "__main__":
    main()
