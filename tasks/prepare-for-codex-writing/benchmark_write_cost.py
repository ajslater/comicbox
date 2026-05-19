# ruff: noqa: D103, T201, INP001, RUF001, RUF003  benchmark script
"""
CBZ write-cost benchmark.

Compares the two write paths in ``comicbox/box/archive/write.py``:

  _patch_zipfile  — open archive in append mode; zf.remove() the
                    existing metadata files; zf.repack() the central
                    directory; append the new metadata files.

  _create_zipfile — write a brand-new zip to a temp path with all
                    non-metadata entries copied in, then atomically
                    rename over the original.

Per the project plan (§2.4): pick a winner per archive size, or across
the board, based on real numbers — so a Codex-driven publisher-rename
batch over 10 000 comics finishes in minutes rather than hours.

Run::

    uv run python tasks/prepare-for-codex-writing/benchmark_write_cost.py
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

# Break the comicbox.formats <-> comicbox.box import cycle before
# importing anything that depends on a fully-initialized comicbox.box.
import comicbox.box  # noqa: F401  ensure comicbox.box is initialized
from comicbox.box import Comicbox

if TYPE_CHECKING:
    from collections.abc import Iterable


# A 1×1 JPEG. Smallest valid JPEG, used to bulk up synthetic CBZs without
# generating multi-MB random data per page.
_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606"
    "07060805070707090908"
    "0a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c"
    "30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d0d18322112"
    "1c32323232323232323232323232323232323232323232323232323232323232323232"
    "32323232323232323232323232323232323232ffc00011080001000103012200"
    "021101031101ffc4001f0000010501010101010100000000000000000102"
    "030405060708090a0bffc400b5100002010303020403050504040000017d010203"
    "00041105122131410613516107227114328191a1082342b1c11552d1f0243362"
    "72820a162434e125f11718191a25262728292a3435363738393a434445464748494a535"
    "455565758595a636465666768696a737475767778797a83848586878889"
    "8a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c"
    "6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f"
    "8f9faffc4001f0100030101010101010101010000000000000102030405060708"
    "090a0bffc400b51100020102040403040705040400010277000102031104052131"
    "061241510761711322328108144291a1b1c109233352f0156272d10a162434e1"
    "25f11718191a262728292a35363738393a434445464748494a535455565758595"
    "a636465666768696a737475767778797a82838485868788898a92939495969798"
    "999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d"
    "6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311"
    "003f00fbfcffd9"
)

_MIN_COMICINFO = (
    b'<?xml version="1.0" encoding="utf-8"?>\n'
    b"<ComicInfo>\n"
    b"  <Publisher>Original</Publisher>\n"
    b"</ComicInfo>\n"
)


def make_synthetic_cbz(path: Path, n_pages: int, *, payload_kb: int = 0) -> Path:
    """Build a CBZ with `n_pages` synthetic pages plus a ComicInfo.xml."""
    payload = _TINY_JPEG + (b"\0" * (payload_kb * 1024))
    with ZipFile(path, "w") as zf:
        zf.writestr(
            "ComicInfo.xml",
            _MIN_COMICINFO,
            compress_type=ZIP_DEFLATED,
            compresslevel=9,
        )
        for i in range(n_pages):
            zf.writestr(
                f"page-{i:04d}.jpg",
                payload,
                compress_type=ZIP_STORED,  # match what comicbox writes
            )
    return path


def time_run(fn, *args, **kwargs) -> float:
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return time.perf_counter() - t0


def run_patch_zipfile(source: Path, work_dir: Path) -> float:
    """Time a single _patch_zipfile run on a fresh copy of `source`."""
    target = work_dir / f"copy-{source.name}"
    shutil.copy(source, target)
    cb = Comicbox(target)
    files = {"ComicInfo.xml": _MIN_COMICINFO}
    try:
        return time_run(cb._patch_zipfile, files, b"")  # noqa: SLF001
    finally:
        cb.close()
        target.unlink(missing_ok=True)


def run_create_zipfile(source: Path, work_dir: Path) -> float:
    """Time a single _create_zipfile run on a fresh copy of `source`."""
    target = work_dir / f"copy-{source.name}"
    shutil.copy(source, target)
    cb = Comicbox(target)
    files = {"ComicInfo.xml": _MIN_COMICINFO}
    try:
        return time_run(cb._create_zipfile, files, b"")  # noqa: SLF001
    finally:
        cb.close()
        # _create_zipfile renames target.with_suffix(".cbz"); cleanup both.
        target.unlink(missing_ok=True)
        target.with_suffix(".cbz").unlink(missing_ok=True)


def bench_size(
    label: str, source: Path, work_dir: Path, n_iter: int
) -> dict[str, dict[str, float]]:
    print(f"\n== {label} ({source.stat().st_size / 1024:.0f} KB) ==", flush=True)
    out: dict[str, dict[str, float]] = {}
    for name, runner in (
        ("patch_zipfile", run_patch_zipfile),
        ("create_zipfile", run_create_zipfile),
    ):
        # Warm-up: filesystem caches make the first run an outlier.
        runner(source, work_dir)
        times = [runner(source, work_dir) for _ in range(n_iter)]
        out[name] = {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
        }
        m = out[name]
        print(
            f"  {name:14s} mean={m['mean'] * 1000:7.1f}ms "
            f"median={m['median'] * 1000:7.1f}ms "
            f"min={m['min'] * 1000:7.1f}ms max={m['max'] * 1000:7.1f}ms",
            flush=True,
        )
    fast, slow = sorted(out.items(), key=lambda kv: kv[1]["median"])
    speedup = slow[1]["median"] / fast[1]["median"]
    print(f"  → {fast[0]} is {speedup:.2f}× faster (median)", flush=True)
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--iter",
        type=int,
        default=5,
        help="Iterations per benchmark (default: 5).",
    )
    parser.add_argument(
        "--sample-cbz",
        type=Path,
        default=None,
        help="Optional: real CBZ to benchmark in addition to synthetic ones.",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        results: dict[str, dict[str, dict[str, float]]] = {}

        # Three synthetic sizes spanning the realistic range.
        sizes = (
            ("synthetic-small (8 pages, ~5KB)", 8, 0),
            ("synthetic-medium (50 pages, ~50KB)", 50, 1),
            ("synthetic-large (200 pages, ~5MB)", 200, 25),
        )
        for label, n_pages, payload_kb in sizes:
            src = work / f"src-{n_pages}.cbz"
            make_synthetic_cbz(src, n_pages, payload_kb=payload_kb)
            results[label] = bench_size(label, src, work, args.iter)

        if args.sample_cbz:
            results[f"real ({args.sample_cbz.name})"] = bench_size(
                f"real ({args.sample_cbz.name})", args.sample_cbz, work, args.iter
            )

        print("\nSummary (median ms):")
        print(f"  {'archive':40s} {'patch':>10s} {'create':>10s} {'winner':>15s}")
        for label, r in results.items():
            patch = r["patch_zipfile"]["median"] * 1000
            create = r["create_zipfile"]["median"] * 1000
            winner = "patch" if patch < create else "create"
            speedup = max(patch, create) / min(patch, create)
            print(
                f"  {label:40s} {patch:>10.1f} {create:>10.1f} "
                f"{winner + f' ({speedup:.2f}×)':>15s}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
