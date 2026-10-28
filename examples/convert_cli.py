"""Use the converter engine without any bot framework.

    python examples/convert_cli.py book.epub pdf
"""
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.converter.engine import available_output_choices, capabilities, convert_file  # noqa: E402
from modules.converter.formats import detect_input_format  # noqa: E402


async def main(path: str, target: str) -> int:
    src = Path(path)
    fmt = detect_input_format(src.name)
    print("Backends:", capabilities())
    print(f".{fmt} can become:", ", ".join(available_output_choices(fmt)) or "(nothing on this host)")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / f"input.{fmt}"
        shutil.copy(src, work)
        result = await convert_file(work, target)
        if not result.ok:
            print("Failed:", result.error)
            return 1
        out = src.with_suffix(f".{target}")
        shutil.copy(result.path, out)
        print("Wrote", out)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    raise SystemExit(asyncio.run(main(sys.argv[1], sys.argv[2])))
