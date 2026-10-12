"""Check exact name==version pins against PyPI without installing anything."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PIN = re.compile(
    r"([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"(?:\[[A-Za-z0-9._,-]+\])?\s*==\s*([A-Za-z0-9][A-Za-z0-9.!+_-]*)"
)


def pypi_json(name, version=None):
    """Return JSON, or None for a 404; other failures remain errors."""
    url = f"https://pypi.org/pypi/{quote(name, safe='')}/"
    if version is not None:
        url += f"{quote(version, safe='')}/"
    request = Request(url + "json", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def check_requirements(lines):
    missing_packages = []
    missing_versions = []
    errors = []
    oldest = None

    for line_number, line in enumerate(lines, start=1):
        pin = line.split("#", 1)[0].strip()
        if not pin:
            continue
        match = PIN.fullmatch(pin)
        if match is None:
            errors.append(f"Line {line_number}: expected an exact name==version pin: {pin}")
            continue
        name, version = match.groups()
        try:
            if pypi_json(name) is None:
                missing_packages.append(name)
                continue
            release = pypi_json(name, version)
            if release is None:
                missing_versions.append(f"{name}=={version}")
                continue
            files = release["urls"]
            if not files:
                errors.append(f"Line {line_number}: {pin} exists but has no uploaded files")
                continue
            uploaded = datetime.fromisoformat(files[0]["upload_time"])
            if oldest is None or uploaded < oldest[0]:
                oldest = (uploaded, name, version)
        except (URLError, OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"Line {line_number}: could not check {pin}: {error}")

    print(f"Dependencies checked: {len(lines)}")
    print(f"Packages not on PyPI: {len(missing_packages)}"
          + (f" ({', '.join(missing_packages)})" if missing_packages else ""))
    print(f"Versions not on PyPI: {len(missing_versions)}"
          + (f" ({', '.join(missing_versions)})" if missing_versions else ""))
    if oldest is None:
        print("Oldest pinned release: none")
    else:
        uploaded, name, version = oldest
        print(f"Oldest pinned release: {name}=={version}({uploaded.year})")
    for error in errors:
        print(error, file=sys.stderr)
    # 2 means incomplete checks; 1 means missing dependencies; 0 means all exist.
    return 2 if errors else int(bool(missing_packages or missing_versions))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", default="requirement.txt",
                        help="requirements file (default: requirement.txt)")
    args = parser.parse_args()
    try:
        lines = Path(args.file).read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as error:
        print(f"Could not read {args.file}: {error}", file=sys.stderr)
        return 2
    return check_requirements(lines)


if __name__ == "__main__":
    sys.exit(main())
