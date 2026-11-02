#!/usr/bin/env python3
"""
Supercell asset decompressor.

Supports the formats implemented here:
  - none: uncompressed input (copied unchanged)
  - lzma: LZMA-alone stream with Supercell's 9-byte size header
  - sc:   SC wrapper around an LZMA-alone stream
  - sc2:  SC2 wrapper around an LZMA-alone stream
  - sig:  Sig: wrapper around an LZMA-alone stream
  - zstd: SC wrapper containing a Zstandard frame (requires `zstandard`)

SCLZ/LZHAM is detected but not decoded by this pure-Python implementation.
The original project uses a bundled LZHAM WebAssembly module; Python's
standard library has no LZHAM decoder.
"""

from __future__ import annotations

import argparse
import lzma
import os
import sys
from pathlib import Path
from typing import Iterable

ZSTD_MAGIC = bytes.fromhex("28 b5 2f fd")
MAX_OUTPUT_SIZE = 2 * 1024 * 1024 * 1024  # safety limit: 2 GiB


class DecompressionError(Exception):
    pass


def read_signature(data: bytes) -> str:
    if data.startswith(bytes.fromhex("5d 00 00")):
        return "lzma"

    if data[:2].lower() == b"sc":
        if len(data) >= 30 and data[26:30].lower() == b"sclz":
            return "sclz"
        if len(data) >= 34 and data[30:34] == ZSTD_MAGIC:
            return "zstd"
        if b"START" in data:
            return "sc2"
        return "sc"

    if data[:4].lower() == b"sig:":
        return "sig"

    return "none"


def _decompress_lzma_payload(payload: bytes) -> bytes:
    """
    The source format stores the 5-byte LZMA properties followed by a
    4-byte uncompressed-size field, then the compressed stream. Python's
    FORMAT_ALONE expects the full 13-byte LZMA-alone header.
    """
    if len(payload) < 9:
        raise DecompressionError("LZMA payload is shorter than its 9-byte header")

    declared_size = int.from_bytes(payload[5:9], "little", signed=True)
    size_field = (
        b"\xff" * 8 if declared_size == -1
        else declared_size.to_bytes(8, "little", signed=False)
    )
    alone_stream = payload[:5] + size_field + payload[9:]

    try:
        dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        result = dec.decompress(alone_stream, max_length=MAX_OUTPUT_SIZE + 1)
    except lzma.LZMAError as exc:
        raise DecompressionError(f"LZMA decompression failed: {exc}") from exc

    if len(result) > MAX_OUTPUT_SIZE:
        raise DecompressionError("Decompressed data exceeds the 2 GiB safety limit")
    if not result and not dec.eof:
        raise DecompressionError("LZMA stream did not produce output or is incomplete")
    return result


def _decompress_zstd(payload: bytes) -> bytes:
    try:
        import zstandard as zstd
    except ImportError as exc:
        raise DecompressionError(
            "Zstandard support needs the optional package. Install it with: "
            "python -m pip install zstandard"
        ) from exc

    try:
        result = zstd.ZstdDecompressor().decompress(
            payload, max_output_size=MAX_OUTPUT_SIZE
        )
    except Exception as exc:
        raise DecompressionError(f"Zstandard decompression failed: {exc}") from exc
    return result


def decompress_bytes(data: bytes) -> tuple[bytes, str]:
    signature = read_signature(data)

    if signature == "none":
        return data, signature

    if signature == "sclz":
        raise DecompressionError(
            "SCLZ/LZHAM was detected, but this standalone Python build does not "
            "include an LZHAM decoder. The source project uses a WebAssembly "
            "LZHAM implementation; this format needs a separate native/Python "
            "LZHAM binding."
        )

    if signature == "zstd":
        # Matches the source project's SC/Zstandard layout: 30-byte wrapper,
        # followed by a Zstandard frame ending before the optional START marker.
        payload = data[30:]
        marker = payload.find(b"START")
        if marker >= 0:
            payload = payload[:marker]
        return _decompress_zstd(payload), signature

    if signature == "sc":
        payload = data[26:]
    elif signature == "sc2":
        payload = data[30:]
        marker = payload.find(b"START")
        if marker >= 0:
            payload = payload[:marker]
    elif signature == "sig":
        if len(data) < 68:
            raise DecompressionError("SIG file is shorter than its 68-byte header")
        payload = data[68:]
    elif signature == "lzma":
        payload = data
    else:
        return data, "none"

    return _decompress_lzma_payload(payload), signature


def iter_input_files(path: Path, recursive: bool) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    if not path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {path}")

    iterator = path.rglob("*") if recursive else path.iterdir()
    for item in sorted(iterator):
        if item.is_file():
            yield item


def output_path_for(source: Path, input_path: Path, output_dir: Path) -> Path:
    if input_path.is_file():
        return output_dir / source.name
    return output_dir / source.relative_to(input_path)


def process_path(input_path: Path, output_dir: Path, recursive: bool,
                 overwrite: bool) -> tuple[int, int, int]:
    files = list(iter_input_files(input_path, recursive))
    if not files:
        print("No files found.")
        return 0, 0, 0

    succeeded = failed = skipped = 0

    for source in files:
        destination = output_path_for(source, input_path, output_dir)
        try:
            raw = source.read_bytes()
            decoded, signature = decompress_bytes(raw)

            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not overwrite:
                print(f"[SKIP] {source} -> output already exists: {destination}")
                skipped += 1
                continue

            destination.write_bytes(decoded)
            status = "COPIED" if signature == "none" else f"DECOMPRESSED:{signature}"
            print(f"[{status}] {source} -> {destination} ({len(raw)} -> {len(decoded)} bytes)")
            succeeded += 1
        except Exception as exc:
            print(f"[ERROR] {source}: {exc}")
            failed += 1

    return succeeded, failed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decompress Supercell assets from a file or folder."
    )
    parser.add_argument("input", nargs="?", help="Input file or folder")
    parser.add_argument(
        "-o", "--output", default="decompressed",
        help="Output folder (default: ./decompressed)"
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true",
        help="Process subfolders recursively"
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite files already present in the output folder"
    )
    args = parser.parse_args()

    input_value = args.input
    if not input_value:
        input_value = input("Enter asset file or folder path: ").strip().strip('"')

    if not input_value:
        print("No input path provided.")
        return 2

    input_path = Path(os.path.expandvars(input_value)).expanduser().resolve()
    output_dir = Path(os.path.expandvars(args.output)).expanduser().resolve()

    try:
        if not input_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {input_path}")
        if input_path.is_dir() and output_dir == input_path:
            raise ValueError("Output folder cannot be the same as the input folder.")
        if input_path.is_file() and output_dir == input_path.parent:
            print("Warning: output is the input file's folder; originals are protected "
                  "unless --overwrite is specified.")

        print(f"Input : {input_path}")
        print(f"Output: {output_dir}")
        print(f"Mode  : {'recursive folder' if input_path.is_dir() and args.recursive else 'file/folder'}")
        print("-" * 72)

        ok, bad, skipped = process_path(
            input_path, output_dir, args.recursive, args.overwrite
        )
        print("-" * 72)
        print(f"Finished. Successful: {ok} | Failed: {bad} | Skipped: {skipped}")
        return 1 if bad else 0

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
