# CBZ Write-Cost Benchmark — Findings

## Question

Plan §2.4 asked: which write path is faster for the CBZ "publisher rename" use
case (a sparse metadata patch that touches the comic's `ComicInfo.xml`,
`comicbox.json`, or `MetronInfo.xml` but leaves every page file alone)?

Two candidates in `comicbox/box/archive/write.py`:

- **`_patch_zipfile`** — opens the archive in append mode, calls `zf.remove()`
  on the existing metadata files, then `zf.repack()` the central directory, then
  appends the new metadata. The image entries are untouched on disk.
- **`_create_zipfile`** — writes a brand-new zip to a temp file, copies every
  non-metadata entry across, writes the new metadata, atomically renames.

The reader has to walk both paths to update CBR/CBT (which always convert to CBZ
via `_create_zipfile`), but the _default_ dispatch on a plain CBZ is
`_patch_zipfile`. Worth confirming that's the right default.

## Benchmark

`tasks/prepare-for-codex-writing/benchmark_write_cost.py`:

- Three synthetic CBZs (8 / 50 / 200 pages, tiny JPEG payloads + zero-byte
  padding for realistic-ish entry sizes).
- The repo's real test fixture (`Captain Science #001-cix.cbz`, ~15 MB, 38 real
  JPEG pages).
- Calls each write method directly with a one-entry `files` dict and an empty
  comment, on a fresh copy of the source CBZ. Seven iterations after a warm-up.

Run on macOS, Python 3.14, APFS (warm filesystem cache):

```
archive                                       patch     create          winner
synthetic-small (8 pages, ~5KB)                 0.3        0.9   patch (3.36×)
synthetic-medium (50 pages, ~50KB)              0.8        2.4   patch (2.94×)
synthetic-large (200 pages, ~5MB)               4.6        9.7   patch (2.09×)
real (Captain Science #001-cix.cbz, 15MB)       1.0       34.1   patch (34.27×)
```

(Times are medians in milliseconds.)

## Why patch wins so decisively

`_patch_zipfile` reads only the central directory of the archive — a few hundred
bytes per entry — and `zf.repack()` rewrites the directory plus the local-header
slots of any removed entries (the metadata file we're overwriting). The page
data on disk is not read, decompressed, recompressed, or re-written.

`_create_zipfile` copies every page entry: read compressed bytes from the source
archive, possibly recompress (the code recompresses with deflate for non-image
entries; images stay `ZIP_STORED`), write to the temp file. For the real 15 MB
fixture that's 38 page reads + 38 page writes per call — every millisecond of
which is wasted work for a publisher rename.

The synthetic-large case is closer (2.09×) because its "pages" are tiny stored
blobs, so `_create_zipfile`'s copy cost is much smaller. The real-world case is
the realistic one — and patch is 34× faster there.

## Conclusion

**No code change needed.** The dispatcher in
`ComicboxArchiveWrite.write_archive_metadata`
(`comicbox/box/archive/write.py:180`) already picks `_patch_zipfile` for CBZ
writes by default. The benchmark confirms that's the correct choice for the
publisher-rename / sparse-write use case Codex needs.

What we **did not** change, and shouldn't:

- `_create_zipfile` is still required for CBR → CBZ conversion (line 185
  branch). RAR can't be edited in place; rebuilding is the only option.
- PDF takes its own path (`_update_pdffile`).
- The `_patch_zipfile` flow keeps removing the prior metadata files via
  `zf.remove() + zf.repack()`. That cost is what shows up here; replacing it
  with an in-place overwrite would leave dead bytes in the central directory
  (and confuse "what is the source of truth?"), so it's the right tradeoff per
  plan §2.4.

## Cost projection for Codex

A "rename publisher across 10 000 comics" batch, ballpark:

- `_patch_zipfile` median ~1 ms × 10 000 = 10 seconds of actual write work.
- Real-world wall time will be dominated by per-file overhead in the comicbox
  pipeline (load, normalize, merge, dump-format, serialize) rather than the
  archive write itself. Profile the pipeline if 10 000 files takes much longer
  than a minute or two.

For a "rename publisher across 100 000 comics" batch the write cost is ~100
seconds — still small. Per-file pipeline overhead becomes the bottleneck faster
than the archive I/O does.

If profiling later shows the pipeline overhead is the real cost, the follow-up
optimization in plan §2.2 — bypassing the full merge pipeline for simple
leaf-replacement patches by editing the on-archive ComicInfo.xml directly —
would help. The benchmark above sets the floor for what the archive layer can
deliver.

## Reproducing

```
uv run python tasks/prepare-for-codex-writing/benchmark_write_cost.py \
    --iter 7 \
    --sample-cbz "tests/files/Captain Science #001-cix.cbz"
```
