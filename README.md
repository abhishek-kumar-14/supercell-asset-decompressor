# Supercell Asset Decompressor (Python)

A standalone Python file/folder utility for identifying and decompressing supported Supercell asset containers.

## Features

- Accepts a single file or a folder.
- Optional recursive folder processing.
- Automatically detects the input signature.
- Writes results to a separate output directory, preserving originals by default.
- Reports successful, skipped, and failed files.
- Supports `none`, `lzma`, `sc`, `sc2`, `sig`, and `zstd` formats.
- Detects `sclz` but reports that LZHAM support is not included in this Python build.

## Requirements

- Python 3.10 or newer.
- Python standard library for LZMA and other built-in functionality.
- Optional: `zstandard` for Zstandard assets.

Install optional Zstandard support:

```bash
python -m pip install zstandard
```

## Usage

### 1. Decompress one file

```bash
python main.py "path/to/asset.sc"
```

Output is written to the `decompressed` folder.

### 2. Decompress a folder

```bash
python main.py "path/to/assets"
```

By default, only files directly inside the folder are processed.

### 3. Include subfolders

```bash
python main.py "path/to/assets" --recursive
```

### 4. Choose an output folder

```bash
python main.py "path/to/assets" --recursive --output "output_assets"
```

### 5. Overwrite existing output files

```bash
python main.py "path/to/assets" --recursive --output "output_assets" --overwrite
```

### 6. Interactive mode

Run without an input argument:

```bash
python main.py
```

Then enter the path to a file or folder when prompted.

## Supported formats

| Signature | Detection | Python build |
|---|---|---|
| `none` | No known compression signature | Copied unchanged |
| `lzma` | Starts with `5d 00 00` | Supported |
| `sc` | Starts with `SC` | Supported |
| `sc2` | `SC` header containing `START` | Supported |
| `sig` | Starts with `Sig:` | Supported |
| `zstd` | SC header with Zstandard magic at offset 30 | Supported with `zstandard` |
| `sclz` | `SCLZ` marker at offset 26 | Detected; LZHAM decoder not bundled |

## Important compatibility note

This Python implementation follows the format detection and LZMA/Zstandard wrapper layout in the supplied `sc-compression` project. The original JavaScript project also bundles an LZHAM WebAssembly decoder for `SCLZ`. That decoder has not been ported or bundled here, so `SCLZ` files will be reported as unsupported rather than silently producing incorrect output.

The source project also uses a Zstandard decoder. Install the optional `zstandard` Python package to process those files.

## Safety

- Input files are never modified.
- Decompressed files are written to the output directory.
- Existing output files are skipped unless `--overwrite` is specified.
- Only process assets you are authorized to inspect or modify.

## Credits

Format behavior is based on the supplied `sc-compression` project by Jean-Baptiste Martin. See the original project and its license before redistributing derived implementations.

## Disclaimer

This is an independent community utility and is not affiliated with or endorsed by Supercell. Supercell and its game names are trademarks of their respective owners.
