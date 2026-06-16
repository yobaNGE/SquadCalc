#!/usr/bin/env python3
"""
Batch-convert exported SquadCalc heightmap folders to PNG.

Expected input layout:

    <input-root>/
      AlBasrah/
        heightmap.json
        meta.json
      Skorpo/
        heightmap.json
        meta.json

Output layout mirrors the input folders:

    <output-root>/
      AlBasrah/
        heightmap.png
      Skorpo/
        heightmap.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from heightmap_json_to_png import (
    check_declared_grid,
    choose_format,
    downsample_mean,
    encode_heights,
    load_heightmap,
    load_meta,
    update_meta,
    write_png,
)


def find_heightmaps(input_root: Path, heightmap_name: str) -> list[Path]:
    return sorted(path for path in input_root.rglob(heightmap_name) if path.is_file())


def js_block(
    *,
    output_name: str,
    output_format: str,
    cols: int,
    rows: int,
    min_height_m: float,
    precision_m: float,
    downsample: int,
) -> dict[str, Any]:
    return {
        "file": output_name,
        "encoding": output_format,
        "cols": cols,
        "rows": rows,
        "minHeightM": min_height_m,
        "precisionM": precision_m,
        "downsample": downsample,
    }


def convert_heightmap(
    *,
    input_root: Path,
    heightmap_json: Path,
    output_root: Path,
    heightmap_name: str,
    meta_name: str,
    output_name: str,
    precision_m: float,
    min_height_m_override: float | None,
    requested_format: str,
    downsample: int,
    update_source_meta: bool,
) -> dict[str, Any]:
    map_dir = heightmap_json.parent
    relative_dir = map_dir.relative_to(input_root)
    output_png = output_root / relative_dir / output_name
    meta_json = map_dir / meta_name
    meta_path = meta_json if meta_json.exists() else None

    print()
    print(f"=== {relative_dir.as_posix() or '.'} ===")
    heights = load_heightmap(heightmap_json)
    meta = load_meta(meta_path)
    check_declared_grid(meta, heights)

    source_rows, source_cols = heights.shape
    heights = downsample_mean(heights, downsample)

    min_height_m = (
        float(min_height_m_override)
        if min_height_m_override is not None
        else float(meta.get("height_min_m", np.min(heights)))
    )

    print(f"Height range: {float(np.min(heights)):.6f}..{float(np.max(heights)):.6f} m")
    print(f"Encoding base minHeightM={min_height_m}, precisionM={precision_m}")

    encoded = encode_heights(heights, min_height_m, precision_m)
    output_format = choose_format(encoded, requested_format)
    write_png(encoded, output_png, output_format)

    rows, cols = heights.shape
    print(f"Wrote: {output_png}")
    print(f"PNG encoding: {output_format}")
    print(f"PNG dimensions: {cols}x{rows}")
    print(f"PNG size: {output_png.stat().st_size / 1024:.1f} KiB")

    if update_source_meta:
        if meta_path is None:
            raise ValueError(f"--update-meta requested, but {meta_json} does not exist")
        update_meta(
            meta_path,
            meta,
            output_path=output_png,
            output_format=output_format,
            source_cols=source_cols,
            source_rows=source_rows,
            cols=cols,
            rows=rows,
            min_height_m=min_height_m,
            precision_m=precision_m,
            downsample=downsample,
        )

    return {
        "mapFolder": relative_dir.as_posix(),
        "inputJson": str(heightmap_json),
        "outputPng": str(output_png),
        "heightmapPng": js_block(
            output_name=output_name,
            output_format=output_format,
            cols=cols,
            rows=rows,
            min_height_m=min_height_m,
            precision_m=precision_m,
            downsample=downsample,
        ),
    }


def write_manifest(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"Manifest written: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert every heightmap.json under an input folder to PNG files."
    )
    parser.add_argument("input_root", type=Path, help="Folder containing map subfolders.")
    parser.add_argument("output_root", type=Path, help="Folder where PNG folders will be written.")
    parser.add_argument(
        "--heightmap-name",
        default="heightmap.json",
        help="Input heightmap file name to search for. Default: heightmap.json",
    )
    parser.add_argument(
        "--meta-name",
        default="meta.json",
        help="Optional metadata file name next to each heightmap. Default: meta.json",
    )
    parser.add_argument(
        "--output-name",
        default="heightmap.png",
        help="Output PNG file name in each result folder. Default: heightmap.png",
    )
    parser.add_argument(
        "--precision-m",
        type=float,
        default=1.0,
        help="Height precision in meters. Default: 1.0",
    )
    parser.add_argument(
        "--min-height-m",
        type=float,
        default=None,
        help="Encoding base height for every map. Default: meta.height_min_m or data min.",
    )
    parser.add_argument(
        "--format",
        choices=["auto", "gray8", "rgb16"],
        default="auto",
        help="PNG encoding. Default: auto",
    )
    parser.add_argument(
        "--downsample",
        type=int,
        default=1,
        help="Spatial downsample factor using block mean. Default: 1",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Write a JSON summary with heightmapPng blocks. Default: <output-root>/heightmap_png_manifest.json",
    )
    parser.add_argument(
        "--update-meta",
        action="store_true",
        help="Add heightmap_png metadata to every source meta.json.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first failed map. Default: continue and report failures.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()

    if not input_root.is_dir():
        raise ValueError(f"Input root is not a directory: {input_root}")

    heightmaps = find_heightmaps(input_root, args.heightmap_name)
    if not heightmaps:
        raise ValueError(f"No {args.heightmap_name} files found under {input_root}")

    print(f"Found {len(heightmaps)} heightmap(s)")
    results: list[dict[str, Any]] = []
    failures: list[tuple[Path, str]] = []

    for heightmap_json in heightmaps:
        try:
            results.append(
                convert_heightmap(
                    input_root=input_root,
                    heightmap_json=heightmap_json,
                    output_root=output_root,
                    heightmap_name=args.heightmap_name,
                    meta_name=args.meta_name,
                    output_name=args.output_name,
                    precision_m=args.precision_m,
                    min_height_m_override=args.min_height_m,
                    requested_format=args.format,
                    downsample=args.downsample,
                    update_source_meta=args.update_meta,
                )
            )
        except Exception as error:
            failures.append((heightmap_json, str(error)))
            print(f"FAILED: {heightmap_json}")
            print(f"  -> {error}")
            if args.fail_fast:
                raise

    manifest = args.manifest or (output_root / "heightmap_png_manifest.json")
    write_manifest(manifest, results)

    print()
    print(f"Converted: {len(results)}")
    print(f"Failed: {len(failures)}")
    if failures:
        for path, error in failures:
            print(f"  - {path}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
