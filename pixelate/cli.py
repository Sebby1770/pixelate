"""Command-line interface for pixelate."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Dict, Optional

import click
from click.core import ParameterSource
from PIL import Image
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from pixelate import __version__
from pixelate.animation import is_animated, pixelate_animation
from pixelate.ascii_art import RAMPS, image_to_ascii, save_ascii
from pixelate.core import (
    HARDWARE_INFO_KEY,
    PALETTE_INFO_KEY,
    collect_images,
    color_usage_report,
    compare_palettes,
    extract_palette,
    make_spritesheet,
    pixelate_image,
    resolve_palette,
    save_image,
)
from pixelate.dithering import DITHER_ALGORITHMS, DITHER_DESCRIPTIONS
from pixelate.export import swatch_sheet
from pixelate.hardware import HARDWARE_MODES, get_hardware_mode
from pixelate.palette_io import load_palette_file, register_palette, save_gpl, save_hex
from pixelate.palettes import PALETTES, get_palette, list_palettes
from pixelate.presets import PRESETS, get_preset, load_presets_file
from pixelate.ui import console, info_panel, print_banner, print_palette_table
from pixelate.upscale import UPSCALERS


def _palette_choices() -> list[str]:
    return list(PALETTES.keys())


def _dither_choices() -> list[str]:
    return list(DITHER_ALGORITHMS.keys())


def _common_convert_options(fn):
    """Shared Click options for convert / batch / sheet."""
    options = [
        click.option(
            "-p", "--palette",
            default="gameboy",
            show_default=True,
            help="Built-in palette name, or 'auto' to extract from the image.",
        ),
        click.option(
            "--palette-file",
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            default=None,
            help="Custom palette file (.hex or .gpl).",
        ),
        click.option(
            "--colors",
            type=click.IntRange(2, 256),
            default=16,
            show_default=True,
            help="Color count when --palette auto.",
        ),
        click.option(
            "--extract-method",
            type=click.Choice(["kmeans", "median-cut"], case_sensitive=False),
            default="kmeans",
            show_default=True,
            help="Auto-palette extraction algorithm.",
        ),
        click.option(
            "--seed",
            type=int,
            default=None,
            help="RNG seed for auto-palette k-means and pixel subsample. Only used with --palette auto.",
        ),
        click.option(
            "-s", "--pixel-size",
            type=click.IntRange(8, 1024),
            default=96,
            show_default=True,
            help='Resolution of longest side, in "logical" pixels.',
        ),
        click.option(
            "--downscale",
            type=click.Choice(["box", "lanczos", "nearest"], case_sensitive=False),
            default="box",
            show_default=True,
            help="Downscale filter (box is authentic/chunky; lanczos blurs; nearest is point-sample).",
        ),
        click.option(
            "-d", "--dither",
            type=click.Choice(_dither_choices(), case_sensitive=False),
            default="floyd",
            show_default=True,
            help="Dithering algorithm.",
        ),
        click.option(
            "-u", "--upscale",
            type=click.IntRange(1, 16),
            default=4,
            show_default=True,
            help="How many output pixels per logical pixel.",
        ),
        click.option(
            "--scale",
            type=click.IntRange(1, 32),
            default=1,
            show_default=True,
            help="Extra nearest-neighbor upscale after pixelate (chunky pixels).",
        ),
        click.option(
            "--saturation",
            type=click.FloatRange(0.0, 3.0),
            default=1.2,
            show_default=True,
            help="Saturation boost applied before quantization.",
        ),
        click.option(
            "--contrast",
            type=click.FloatRange(0.0, 3.0),
            default=1.0,
            show_default=True,
            help="Contrast multiplier before quantization.",
        ),
        click.option("--invert", is_flag=True, help="Invert colors before palette."),
        click.option("--edges", is_flag=True, help="Edge-aware sharpen pre-pass."),
        click.option("--crt", is_flag=True, help="Apply CRT glow + vignette."),
        click.option("--scanlines", is_flag=True, help="Overlay horizontal scanlines."),
        click.option(
            "--phosphor",
            is_flag=True,
            help="RGB phosphor column mask (after CRT, before scanlines).",
        ),
        click.option(
            "--posterize",
            type=click.IntRange(2, 16),
            default=None,
            help="Posterize each channel to N levels (2–16) before quantize.",
        ),
        click.option(
            "--bayer-size",
            type=click.Choice(["2", "4", "8"], case_sensitive=False),
            default="4",
            show_default=True,
            help="Bayer matrix size (ignored unless --dither bayer).",
        ),
        click.option(
            "--colorspace",
            "--distance",
            "colorspace",
            type=click.Choice(["lab", "rgb", "ciede2000"], case_sensitive=False),
            default="lab",
            show_default=True,
            help="Palette matching: CIE76 Lab, Euclidean RGB, or CIEDE2000.",
        ),
        click.option(
            "--serpentine/--no-serpentine",
            default=True,
            show_default=True,
            help="Serpentine error diffusion (even rows L→R, odd rows R→L).",
        ),
        click.option(
            "--report",
            is_flag=True,
            help="Print color-usage report (palette color pixel counts).",
        ),
        click.option(
            "--preset",
            default=None,
            metavar="NAME",
            help="Named recipe (see `pixelate presets`). Flags you type win.",
        ),
        click.option(
            "--presets-file",
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            default=None,
            help="JSON file of extra presets {name: {option: value}}.",
        ),
        click.option(
            "--hardware",
            type=click.Choice(_hardware_choices(), case_sensitive=False),
            default=None,
            help="Emulate a machine's attribute clash (see `pixelate hardware`).",
        ),
        click.option(
            "--upscaler",
            type=click.Choice(list(UPSCALERS), case_sensitive=False),
            default="nearest",
            show_default=True,
            help="Upscale filter: nearest, or palette-locked Scale2x/3x/4x.",
        ),
        click.option(
            "--outline",
            type=click.IntRange(0, 8),
            default=0,
            show_default=True,
            help="Outline thickness around the foreground (art pixels).",
        ),
        click.option(
            "--outline-color",
            default=None,
            metavar="HEX",
            help="Outline color (default: darkest palette color).",
        ),
        click.option("--grid", is_flag=True, help="Draw a pixel grid over the art."),
        click.option(
            "--chromatic",
            type=click.IntRange(0, 16),
            default=0,
            show_default=True,
            help="Red/blue channel split in output pixels.",
        ),
        click.option(
            "--color-bleed",
            type=click.FloatRange(0.0, 1.0),
            default=0.0,
            show_default=True,
            help="NTSC chroma bleed strength.",
        ),
        click.option(
            "--curvature",
            type=click.FloatRange(0.0, 0.5),
            default=0.0,
            show_default=True,
            help="CRT barrel curvature (try 0.06).",
        ),
        click.option(
            "--cleanup",
            type=click.IntRange(0, 4),
            default=0,
            show_default=True,
            help="Orphan-pixel cleanup passes on the art grid.",
        ),
    ]
    fn = _studio_options(fn)
    for opt in reversed(options):
        fn = opt(fn)
    return fn


_STUDIO_KEYS = (
    "preset", "presets_file", "hardware", "upscaler", "outline", "outline_color",
    "grid", "chromatic", "color_bleed", "curvature", "cleanup",
)
_EXTRA_META = "pixelate_extra"
_PRESET_META = "pixelate_preset"


def _hardware_choices() -> list[str]:
    names = list(HARDWARE_MODES)
    for mode in HARDWARE_MODES.values():
        names.extend(mode.aliases)
    return names


def _parse_hex(value: str) -> tuple:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise click.BadParameter(f"'{value}' is not a #RRGGBB color", param_hint="--outline-color")
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise click.BadParameter(f"'{value}' is not a #RRGGBB color", param_hint="--outline-color") from exc


def _studio_options(fn):
    """Pop 3.0 options into ctx.meta and apply --preset to untouched flags."""

    @functools.wraps(fn)
    def wrapper(*args, **kw):
        ctx = click.get_current_context()
        extras: Dict[str, Any] = {k: kw.pop(k) for k in _STUDIO_KEYS if k in kw}
        presets_file = extras.pop("presets_file", None)
        if presets_file is not None:
            try:
                load_presets_file(presets_file)
            except (ValueError, OSError) as exc:
                raise click.ClickException(f"Could not load presets: {exc}") from exc
        preset_name = extras.pop("preset", None)
        if preset_name:
            try:
                preset = get_preset(preset_name)
            except KeyError as exc:
                raise click.ClickException(str(exc.args[0])) from exc
            for key, value in preset.options.items():
                source = ctx.get_parameter_source(key)
                if source not in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP):
                    continue  # typed on the command line (or not on this command)
                if key in kw:
                    kw[key] = str(value) if key == "bayer_size" else value
                elif key in extras:
                    extras[key] = value
            ctx.meta[_PRESET_META] = preset
        if extras.get("outline_color"):
            extras["outline_color"] = _parse_hex(str(extras["outline_color"]))
        if (
            extras.get("hardware")
            and "pixel_size" in kw
            and ctx.get_parameter_source("pixel_size") in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP)
            and not (ctx.meta.get(_PRESET_META) and "pixel_size" in ctx.meta[_PRESET_META].options)
        ):
            kw["pixel_size"] = get_hardware_mode(extras["hardware"]).pixel_size
        ctx.meta[_EXTRA_META] = extras
        return fn(*args, **kw)

    return wrapper


def _studio_summary(extras: Dict[str, Any]) -> str:
    bits = []
    if extras.get("hardware"):
        bits.append(f"hardware={get_hardware_mode(extras['hardware']).name}")
    if extras.get("upscaler", "nearest") != "nearest":
        bits.append(f"upscaler={extras['upscaler']}")
    for key in ("outline", "chromatic", "color_bleed", "curvature", "cleanup"):
        if extras.get(key):
            bits.append(f"{key.replace('_', '-')}={extras[key]}")
    if extras.get("grid"):
        bits.append("grid")
    return " ".join(bits)


def _validate_palette_name(palette: str, palette_file: Optional[Path]) -> None:
    if palette_file is not None:
        return
    ctx = click.get_current_context(silent=True)
    if ctx is not None and ctx.meta.get(_EXTRA_META, {}).get("hardware"):
        return
    if palette.lower().strip() == "auto":
        return
    # Allow path-as-palette or registered name
    p = Path(palette)
    if p.is_file():
        return
    if palette.lower().strip() not in PALETTES:
        available = ", ".join(sorted(PALETTES))
        raise click.ClickException(
            f"Unknown palette '{palette}'. Available: {available}\n"
            "Or pass 'auto', or a .hex/.gpl file with --palette-file."
        )


def _palette_label(
    palette: str,
    palette_file: Optional[Path],
    colors: int = 16,
) -> str:
    ctx = click.get_current_context(silent=True)
    hw = ctx.meta.get(_EXTRA_META, {}).get("hardware") if ctx is not None else None
    if hw:
        mode = get_hardware_mode(hw)
        return f"hw:{mode.name} — {mode.title} ({len(mode.palette)} colors, {mode.colors_per_cell}/cell)"
    if palette_file is not None:
        loaded = load_palette_file(palette_file)
        return f"file:{palette_file.name} ({len(loaded)} colors)"
    if palette.lower().strip() == "auto":
        return f"auto ({colors} colors)"
    try:
        resolved = resolve_palette(palette)
        return f"{palette} ({len(resolved)} colors)"
    except Exception:
        return palette


def _print_color_report(result, palette_colors) -> None:
    """Print a rich table of palette color usage for a converted image."""
    report = color_usage_report(result, palette=palette_colors)
    table = Table(
        title="[bold cyan]Color usage report[/bold cyan]",
        border_style="green",
        header_style="bold magenta",
    )
    table.add_column("RGB", style="cyan")
    table.add_column("Swatch", justify="center")
    table.add_column("Pixels", style="yellow", justify="right")
    table.add_column("%", style="white", justify="right")

    for (r, g, b), count, pct in report:
        swatch = f"\x1b[48;2;{r};{g};{b}m    \x1b[0m"
        table.add_row(f"({r:3d},{g:3d},{b:3d})", swatch, f"{count:,}", f"{pct:5.1f}%")

    console.print()
    console.print(table)


def _convert_kwargs(
    palette: str,
    palette_file: Path | None,
    pixel_size: int,
    dither: str,
    upscale: int,
    saturation: float,
    crt: bool,
    scanlines: bool,
    colors: int = 16,
    extract_method: str = "kmeans",
    scale: int = 1,
    edges: bool = False,
    invert: bool = False,
    contrast: float = 1.0,
    colorspace: str = "lab",
    serpentine: bool = True,
    phosphor: bool = False,
    posterize: Optional[int] = None,
    bayer_size: int | str = 4,
    seed: Optional[int] = None,
    downscale: str = "box",
) -> dict:
    return dict(
        palette=palette,
        pixel_size=pixel_size,
        dither=dither,
        upscale=upscale,
        saturation=saturation,
        crt=crt,
        scanlines=scanlines,
        palette_file=palette_file,
        colors=colors,
        extract_method=extract_method,
        scale=scale,
        edges=edges,
        invert=invert,
        contrast=contrast,
        colorspace=colorspace,
        serpentine=serpentine,
        phosphor=phosphor,
        posterize=posterize,
        bayer_size=int(bayer_size),
        seed=seed,
        downscale=downscale,
        **_studio_extras(),
    )


def _studio_extras() -> Dict[str, Any]:
    """3.0 options captured by :func:`_studio_options` (printed once)."""
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return {}
    extras = dict(ctx.meta.get(_EXTRA_META, {}))
    if not ctx.meta.get("pixelate_announced"):
        ctx.meta["pixelate_announced"] = True
        preset = ctx.meta.get(_PRESET_META)
        if preset is not None:
            console.print(
                f"[cyan]Preset:[/cyan]    [yellow]{preset.name}[/yellow] [dim]— {preset.description}[/dim]"
            )
        summary = _studio_summary(extras)
        if summary:
            console.print(f"[cyan]Studio:[/cyan]    {summary}")
    return extras


def _picklable_convert_kwargs(kwargs: dict) -> dict:
    """Copy convert kwargs with Path values as strings (spawn-safe)."""
    out = dict(kwargs)
    pf = out.get("palette_file")
    if pf is not None:
        out["palette_file"] = str(pf)
    return out


def _batch_convert_one(payload: dict) -> str:
    """Convert a single batch image. Module-level so ProcessPoolExecutor can pickle it."""
    src = Path(payload["src"])
    input_dir = Path(payload["input_dir"])
    output_dir = Path(payload["output_dir"])
    kwargs = dict(payload["kwargs"])
    pf = kwargs.get("palette_file")
    if pf is not None:
        kwargs["palette_file"] = Path(pf)

    rel = src.relative_to(input_dir) if src.is_relative_to(input_dir) else Path(src.name)
    out_name = Path(rel).stem + "_pixel"
    if is_animated(src):
        dest = output_dir / Path(rel).with_name(out_name + ".gif")
        dest.parent.mkdir(parents=True, exist_ok=True)
        pixelate_animation(src, output=dest, **kwargs)
    else:
        dest = output_dir / Path(rel).with_name(out_name + ".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        result = pixelate_image(src, **kwargs)
        save_image(
            result,
            dest,
            palette=result.info.get(PALETTE_INFO_KEY),
        )
    return str(dest)


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="pixelate")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """PIXELATE — turn any image into retro pixel art."""
    if ctx.invoked_subcommand is None:
        print_banner()
        click.echo(ctx.get_help())


@cli.command("convert")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "-o", "--output", "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output file path. Default: <input>_pixel.png (or .gif for animation).",
)
@_common_convert_options
def convert_cmd(
    input_path: Path,
    output_path: Path | None,
    palette: str,
    palette_file: Path | None,
    colors: int,
    extract_method: str,
    seed: int | None,
    pixel_size: int,
    downscale: str,
    dither: str,
    upscale: int,
    scale: int,
    saturation: float,
    contrast: float,
    invert: bool,
    edges: bool,
    crt: bool,
    scanlines: bool,
    phosphor: bool,
    posterize: int | None,
    bayer_size: str,
    colorspace: str,
    serpentine: bool,
    report: bool,
) -> None:
    """Convert IMAGE to retro pixel art (auto-detects animated GIF/WebP)."""
    print_banner()
    _validate_palette_name(palette, palette_file)

    animated = is_animated(input_path)
    if output_path is None:
        if animated:
            output_path = input_path.with_name(f"{input_path.stem}_pixel.gif")
        else:
            output_path = input_path.with_name(f"{input_path.stem}_pixel.png")

    effects = []
    if crt:
        effects.append("CRT")
    if scanlines:
        effects.append("scanlines")
    if phosphor:
        effects.append("phosphor")
    if posterize is not None:
        effects.append(f"posterize:{posterize}")
    if edges:
        effects.append("edges")
    if invert:
        effects.append("invert")
    effects_str = " ".join(effects) if effects else "none"

    kwargs = _convert_kwargs(
        palette, palette_file, pixel_size, dither, upscale, saturation,
        crt, scanlines, colors, extract_method, scale, edges, invert, contrast,
        colorspace, serpentine, phosphor, posterize, bayer_size, seed,
        downscale=downscale,
    )

    info_panel(
        "[bold]Converting[/bold]",
        (
            f"[cyan]Source:[/cyan]    {input_path}\n"
            f"[cyan]Palette:[/cyan]   [yellow]{_palette_label(palette, palette_file, colors)}[/yellow]\n"
            f"[cyan]Resolution:[/cyan] {pixel_size}px × {upscale}× upscale"
            f"{f' × {scale}× scale' if scale > 1 else ''}\n"
            f"[cyan]Downscale:[/cyan] {downscale}\n"
            f"[cyan]Dither:[/cyan]    {dither}"
            f"{'' if serpentine else ' (no serpentine)'}\n"
            f"[cyan]Match:[/cyan]     {colorspace}\n"
            f"[cyan]Contrast:[/cyan]  {contrast}\n"
            f"[cyan]Animated:[/cyan]  {'yes' if animated else 'no'}\n"
            f"[cyan]Effects:[/cyan]   {effects_str}"
        ),
    )

    with Progress(
        SpinnerColumn(style="green"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="green", finished_style="bright_green"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[green]Pixelating...", total=None)
        if animated:
            first = pixelate_animation(
                input_path,
                output=output_path,
                **kwargs,
            )
            assert isinstance(first, Image.Image)
            result = first
            size_label = f"{result.size[0]}×{result.size[1]}"
            saved = output_path
        else:
            result = pixelate_image(input_path, **kwargs)
            saved = save_image(
                result,
                output_path,
                palette=result.info.get(PALETTE_INFO_KEY),
            )
            size_label = f"{result.size[0]}×{result.size[1]}"
        progress.update(task, completed=1, total=1)

    console.print(
        f"[bold green]✓[/bold green] Saved: [cyan]{saved}[/cyan]  "
        f"[dim]({size_label}{' animated' if animated else ''})[/dim]"
    )

    clash = result.info.get(HARDWARE_INFO_KEY) if not animated else None
    if clash:
        console.print(
            f"[cyan]Clash:[/cyan]     {clash['mode']} · {clash['cells']} cells · "
            f"{clash['distinct_cell_sets']} distinct cell sets · {clash['colors_used']} colors used"
        )

    if report and not animated:
        pal = result.info.get(PALETTE_INFO_KEY)
        if pal is None:
            if palette_file is not None:
                pal = resolve_palette(palette, palette_file=palette_file)
            elif palette.lower().strip() == "auto":
                pal = extract_palette(result, n=colors, method=extract_method)
            else:
                pal = resolve_palette(palette)
        _print_color_report(result, pal)


@cli.command("batch")
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "-o", "--output", "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    required=True,
    help="Directory for converted images.",
)
@click.option("--recursive", "-r", is_flag=True, help="Scan subdirectories.")
@click.option(
    "--jobs",
    type=click.IntRange(1, 32),
    default=1,
    show_default=True,
    help="Parallel workers (ProcessPoolExecutor when greater than 1; threads on spawn failure).",
)
@_common_convert_options
def batch_cmd(
    input_dir: Path,
    output_dir: Path,
    recursive: bool,
    jobs: int,
    palette: str,
    palette_file: Path | None,
    colors: int,
    extract_method: str,
    seed: int | None,
    pixel_size: int,
    downscale: str,
    dither: str,
    upscale: int,
    scale: int,
    saturation: float,
    contrast: float,
    invert: bool,
    edges: bool,
    crt: bool,
    scanlines: bool,
    phosphor: bool,
    posterize: int | None,
    bayer_size: str,
    colorspace: str,
    serpentine: bool,
    report: bool,  # accepted but not printed per-file in batch
) -> None:
    """Batch-convert all images in INPUT_DIR into OUTPUT_DIR."""
    print_banner()
    _validate_palette_name(palette, palette_file)

    images = collect_images([input_dir], recursive=recursive)
    if not images:
        raise click.ClickException(f"No images found in {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    kwargs = _convert_kwargs(
        palette, palette_file, pixel_size, dither, upscale, saturation,
        crt, scanlines, colors, extract_method, scale, edges, invert, contrast,
        colorspace, serpentine, phosphor, posterize, bayer_size, seed,
        downscale=downscale,
    )

    info_panel(
        "[bold]Batch convert[/bold]",
        (
            f"[cyan]Input:[/cyan]     {input_dir}\n"
            f"[cyan]Output:[/cyan]    {output_dir}\n"
            f"[cyan]Images:[/cyan]    {len(images)}\n"
            f"[cyan]Jobs:[/cyan]      {jobs}\n"
            f"[cyan]Palette:[/cyan]   [yellow]{_palette_label(palette, palette_file, colors)}[/yellow]\n"
            f"[cyan]Dither:[/cyan]    {dither}"
        ),
    )

    ok = 0
    errors: list[str] = []
    packed_kwargs = _picklable_convert_kwargs(kwargs)
    payloads = [
        {
            "src": str(src),
            "input_dir": str(input_dir),
            "output_dir": str(output_dir),
            "kwargs": packed_kwargs,
        }
        for src in images
    ]

    with Progress(
        SpinnerColumn(style="green"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="green", finished_style="bright_green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Converting...", total=len(images))
        if jobs <= 1:
            for payload in payloads:
                try:
                    _batch_convert_one(payload)
                    ok += 1
                except Exception as exc:  # noqa: BLE001 — report and continue batch
                    errors.append(f"{Path(str(payload['src'])).name}: {exc}")
                progress.advance(task)
        else:
            from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

            def _drain(executor) -> tuple[int, list[str]]:
                n_ok = 0
                n_err: list[str] = []
                with executor:
                    futures = {
                        executor.submit(_batch_convert_one, p): Path(str(p["src"])).name
                        for p in payloads
                    }
                    for fut in as_completed(futures):
                        name = futures[fut]
                        try:
                            fut.result()
                            n_ok += 1
                        except Exception as exc:  # noqa: BLE001 — report and continue batch
                            n_err.append(f"{name}: {exc}")
                        progress.advance(task)
                return n_ok, n_err

            try:
                n_ok, n_err = _drain(ProcessPoolExecutor(max_workers=jobs))
            except Exception:
                n_ok, n_err = _drain(ThreadPoolExecutor(max_workers=jobs))
            ok += n_ok
            errors.extend(n_err)

    console.print(f"[bold green]✓[/bold green] Converted {ok}/{len(images)} images → [cyan]{output_dir}[/cyan]")
    for err in errors:
        console.print(f"[bold red]✗[/bold red] {err}")
    if report:
        console.print("[dim]Note: --report is shown on single convert, not batch.[/dim]")
    if errors:
        raise click.ClickException(f"{len(errors)} file(s) failed in batch convert")


@cli.command("sheet")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o", "--output", "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("spritesheet.png"),
    show_default=True,
    help="Output spritesheet path.",
)
@click.option(
    "--cols",
    type=click.IntRange(1, 64),
    default=4,
    show_default=True,
    help="Number of columns in the sheet.",
)
@click.option(
    "--padding",
    type=click.IntRange(0, 64),
    default=0,
    show_default=True,
    help="Padding pixels between tiles.",
)
@click.option(
    "--convert/--no-convert",
    default=True,
    show_default=True,
    help="Pixelate each image before tiling (disable to stitch as-is).",
)
@_common_convert_options
def sheet_cmd(
    paths: tuple[Path, ...],
    output_path: Path,
    cols: int,
    padding: int,
    convert: bool,
    palette: str,
    palette_file: Path | None,
    colors: int,
    extract_method: str,
    seed: int | None,
    pixel_size: int,
    downscale: str,
    dither: str,
    upscale: int,
    scale: int,
    saturation: float,
    contrast: float,
    invert: bool,
    edges: bool,
    crt: bool,
    scanlines: bool,
    phosphor: bool,
    posterize: int | None,
    bayer_size: str,
    colorspace: str,
    serpentine: bool,
    report: bool,
) -> None:
    """Stitch images (or a directory) into a spritesheet.

    Each path may be a file or directory. By default images are pixelated
    first, then arranged into a grid of COLS columns.
    """
    print_banner()
    if convert:
        _validate_palette_name(palette, palette_file)

    files = collect_images(list(paths))
    if not files:
        raise click.ClickException("No images found for spritesheet")

    kwargs = _convert_kwargs(
        palette, palette_file, pixel_size, dither, upscale, saturation,
        crt, scanlines, colors, extract_method, scale, edges, invert, contrast,
        colorspace, serpentine, phosphor, posterize, bayer_size, seed,
        downscale=downscale,
    )

    info_panel(
        "[bold]Spritesheet[/bold]",
        (
            f"[cyan]Inputs:[/cyan]    {len(files)} images\n"
            f"[cyan]Columns:[/cyan]   {cols}\n"
            f"[cyan]Convert:[/cyan]   {'yes' if convert else 'no (stitch as-is)'}\n"
            f"[cyan]Palette:[/cyan]   [yellow]{_palette_label(palette, palette_file, colors)}[/yellow]\n"
            f"[cyan]Output:[/cyan]    {output_path}"
        ),
    )

    tiles = []
    with Progress(
        SpinnerColumn(style="green"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="green", finished_style="bright_green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[green]Building sheet...", total=len(files))
        from PIL import Image, ImageOps

        for src in files:
            if convert:
                tile = pixelate_image(src, **kwargs)
            else:
                tile = ImageOps.exif_transpose(Image.open(src))
            tiles.append(tile)
            progress.advance(task)

    sheet = make_spritesheet(tiles, cols=cols, padding=padding)
    saved = save_image(sheet, output_path)
    console.print(
        f"[bold green]✓[/bold green] Spritesheet: [cyan]{saved}[/cyan]  "
        f"[dim]({sheet.size[0]}×{sheet.size[1]}, {len(tiles)} tiles)[/dim]"
    )


@cli.command("compare")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--palettes",
    "palette_list",
    default="gameboy,nes,pico8,c64",
    show_default=True,
    help="Comma-separated palette names to compare.",
)
@click.option(
    "-o", "--output", "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output collage path. Default: <input>_compare.png",
)
@click.option(
    "-s", "--pixel-size",
    type=click.IntRange(8, 1024),
    default=64,
    show_default=True,
)
@click.option(
    "-d", "--dither",
    type=click.Choice(_dither_choices(), case_sensitive=False),
    default="floyd",
    show_default=True,
)
@click.option(
    "-u", "--upscale",
    type=click.IntRange(1, 16),
    default=2,
    show_default=True,
)
@click.option(
    "--cols",
    type=click.IntRange(1, 16),
    default=None,
    help="Grid columns (default: auto, max 4).",
)
@click.option("--no-label", is_flag=True, help="Hide palette name labels.")
@click.option(
    "--colorspace",
    "--distance",
    "colorspace",
    type=click.Choice(["lab", "rgb", "ciede2000"], case_sensitive=False),
    default="lab",
    show_default=True,
    help="Palette matching: CIE76 Lab, Euclidean RGB, or CIEDE2000.",
)
@click.option(
    "--serpentine/--no-serpentine",
    default=True,
    show_default=True,
    help="Serpentine error diffusion.",
)
def compare_cmd(
    input_path: Path,
    palette_list: str,
    output_path: Path | None,
    pixel_size: int,
    dither: str,
    upscale: int,
    cols: int | None,
    no_label: bool,
    colorspace: str,
    serpentine: bool,
) -> None:
    """Compare multiple palettes on one image (labeled collage)."""
    print_banner()
    names = [n.strip() for n in palette_list.split(",") if n.strip()]
    if not names:
        raise click.ClickException("No palettes specified. Use --palettes gameboy,nes,...")

    for name in names:
        if name.lower().startswith("hw:"):
            try:
                get_hardware_mode(name[3:])
            except KeyError as exc:
                raise click.ClickException(str(exc.args[0])) from exc
            continue
        if name.lower() not in PALETTES and name.lower() != "auto":
            p = Path(name)
            if not p.is_file():
                raise click.ClickException(
                    f"Unknown palette '{name}'. Run `pixelate palettes` for the list."
                )

    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_compare.png")

    info_panel(
        "[bold]Palette compare[/bold]",
        (
            f"[cyan]Source:[/cyan]   {input_path}\n"
            f"[cyan]Palettes:[/cyan] [yellow]{', '.join(names)}[/yellow]\n"
            f"[cyan]Output:[/cyan]   {output_path}"
        ),
    )

    with Progress(
        SpinnerColumn(style="green"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("[green]Building collage...", total=None)
        collage = compare_palettes(
            input_path,
            names,
            pixel_size=pixel_size,
            dither=dither,
            upscale=upscale,
            cols=cols,
            label=not no_label,
            colorspace=colorspace,
            serpentine=serpentine,
        )
        saved = save_image(collage, output_path)

    console.print(
        f"[bold green]✓[/bold green] Compare grid: [cyan]{saved}[/cyan]  "
        f"[dim]({collage.size[0]}×{collage.size[1]}, {len(names)} palettes)[/dim]"
    )


@cli.command("ascii")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-w", "--width", type=click.IntRange(20, 400), default=100, show_default=True)
@click.option("-r", "--ramp", default="dense", show_default=True,
              help=f"One of {', '.join(RAMPS)} or a custom char ramp.")
@click.option("--color/--no-color", default=True, show_default=True,
              help="Use 24-bit ANSI color in the terminal output.")
@click.option("--invert", is_flag=True, help="Invert the ramp (light backgrounds).")
@click.option("-o", "--output", "output_path",
              type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="Save the result to a .txt file (color codes stripped).")
def ascii_cmd(input_path: Path, width: int, ramp: str, color: bool,
              invert: bool, output_path: Path | None) -> None:
    """Render IMAGE as ASCII / ANSI art."""
    art = image_to_ascii(
        input_path,
        width=width,
        ramp=ramp,
        color=color,
        invert=invert,
    )
    click.echo(art)
    if output_path:
        saved = save_ascii(art, output_path)
        console.print(f"\n[bold green]✓[/bold green] Saved: [cyan]{saved}[/cyan]")


@cli.command("extract")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "-o", "--output", "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output palette path (.gpl or .hex).",
)
@click.option(
    "--colors",
    type=click.IntRange(1, 256),
    default=16,
    show_default=True,
    help="Number of colors to extract.",
)
@click.option(
    "--extract-method",
    type=click.Choice(["kmeans", "median-cut"], case_sensitive=False),
    default="kmeans",
    show_default=True,
)
@click.option(
    "--seed",
    type=int,
    default=None,
    help="RNG seed for k-means (default 0).",
)
@click.option(
    "--hex",
    "write_hex",
    is_flag=True,
    help="Also write a .hex file next to the .gpl (same stem).",
)
def extract_cmd(
    input_path: Path,
    output_path: Path,
    colors: int,
    extract_method: str,
    seed: int | None,
    write_hex: bool,
) -> None:
    """Extract N colors from IMAGE and write a GIMP .gpl (optional .hex)."""
    print_banner()
    pal = extract_palette(input_path, n=colors, method=extract_method, seed=seed)
    name = input_path.stem
    suffix = output_path.suffix.lower()
    if suffix == ".hex":
        saved = save_hex(pal, output_path)
        console.print(
            f"[bold green]✓[/bold green] Wrote {len(pal)} colors → [cyan]{saved}[/cyan]"
        )
        return
    saved = save_gpl(pal, output_path, name=name)
    extra = ""
    if write_hex:
        hex_path = save_hex(pal, output_path.with_suffix(".hex"))
        extra = f"  + [cyan]{hex_path}[/cyan]"
    console.print(
        f"[bold green]✓[/bold green] Wrote {len(pal)} colors → [cyan]{saved}[/cyan]{extra}"
    )


@cli.command("palettes")
@click.option(
    "--load",
    "load_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Preview colors from a .hex/.gpl file without registering.",
)
@click.option(
    "--register-as",
    default=None,
    help="With --load, also register the palette under this name for the session.",
)
@click.option(
    "--save-gpl",
    "save_gpl_name",
    default=None,
    help="Dump a built-in palette to a GIMP .gpl file (requires -o).",
)
@click.option(
    "-o", "--output", "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Destination for --save-gpl.",
)
def palettes_cmd(
    load_file: Path | None,
    register_as: str | None,
    save_gpl_name: str | None,
    output_path: Path | None,
) -> None:
    """List all built-in palettes (optionally load or dump a .gpl)."""
    print_banner()

    if save_gpl_name:
        try:
            colors = get_palette(save_gpl_name)
        except KeyError as exc:
            raise click.ClickException(str(exc)) from exc
        if output_path is None:
            output_path = Path(f"{save_gpl_name.lower().strip()}.gpl")
        saved = save_gpl(colors, output_path, name=save_gpl_name)
        console.print(
            f"[bold green]✓[/bold green] Saved [yellow]{save_gpl_name}[/yellow] "
            f"({len(colors)} colors) → [cyan]{saved}[/cyan]\n"
        )
        return

    if load_file is not None:
        colors = load_palette_file(load_file)
        name = register_as or load_file.stem
        if register_as:
            register_palette(register_as, colors)
            console.print(
                f"[bold green]✓[/bold green] Registered [yellow]{register_as}[/yellow] "
                f"({len(colors)} colors) from [cyan]{load_file}[/cyan]\n"
            )
        else:
            console.print(
                f"[bold cyan]{name}[/bold cyan] "
                f"[dim]({len(colors)} colors from {load_file})[/dim]\n"
            )
        line = []
        for r, g, b in colors:
            line.append(f"\x1b[48;2;{r};{g};{b}m      \x1b[0m")
        click.echo("".join(line))
        click.echo("".join(line))
        click.echo()

    print_palette_table(list_palettes())


@cli.command("preview")
@click.argument("palette_name")
def preview_cmd(palette_name: str) -> None:
    """Print a swatch of a palette in your terminal."""
    try:
        palette = resolve_palette(palette_name)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    console.print(f"\n[bold cyan]{palette_name}[/bold cyan] "
                  f"[dim]({len(palette)} colors)[/dim]\n")
    line = []
    for r, g, b in palette:
        line.append(f"\x1b[48;2;{r};{g};{b}m      \x1b[0m")
    click.echo("".join(line))
    click.echo("".join(line))  # double-row for chunkier swatches
    click.echo()


if __name__ == "__main__":
    cli()


@cli.command("hardware")
def hardware_cmd() -> None:
    """List hardware modes (attribute-clash emulation)."""
    print_banner()
    table = Table(title="[bold cyan]Hardware modes[/bold cyan]", border_style="green",
                  header_style="bold magenta")
    table.add_column("Name", style="yellow")
    table.add_column("Machine", style="cyan")
    table.add_column("Cell", justify="center")
    table.add_column("Colors/cell", justify="center")
    table.add_column("Native", justify="center")
    table.add_column("Rules", style="white")
    for mode in HARDWARE_MODES.values():
        aliases = f" [dim]({', '.join(mode.aliases)})[/dim]" if mode.aliases else ""
        table.add_row(
            mode.name + aliases, mode.title, f"{mode.cell[0]}×{mode.cell[1]}",
            str(mode.colors_per_cell), f"{mode.native[0]}×{mode.native[1]}", mode.notes,
        )
    console.print(table)
    console.print("[dim]pixelate convert photo.jpg --hardware zx --pixel-size 256 --dither pattern[/dim]")


@cli.command("presets")
@click.option("--file", "presets_file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None, help="Also load presets from this JSON file.")
def presets_cmd(presets_file: Optional[Path]) -> None:
    """List named presets."""
    print_banner()
    if presets_file is not None:
        try:
            load_presets_file(presets_file)
        except (ValueError, OSError) as exc:
            raise click.ClickException(f"Could not load presets: {exc}") from exc
    table = Table(title="[bold cyan]Presets[/bold cyan]", border_style="green",
                  header_style="bold magenta")
    table.add_column("Name", style="yellow")
    table.add_column("Look", style="white")
    table.add_column("Options", style="dim")
    for preset in PRESETS.values():
        opts = " ".join(f"{k}={v}" for k, v in preset.options.items())
        table.add_row(preset.name, preset.description, opts)
    console.print(table)
    console.print("[dim]pixelate convert photo.jpg --preset zx-loading-screen[/dim]")


@cli.command("dithers")
def dithers_cmd() -> None:
    """List dithering algorithms."""
    print_banner()
    table = Table(title="[bold cyan]Dithers[/bold cyan]", border_style="green",
                  header_style="bold magenta")
    table.add_column("Name", style="yellow")
    table.add_column("What it does", style="white")
    for name, desc in DITHER_DESCRIPTIONS.items():
        table.add_row(name, desc)
    console.print(table)


@cli.command("swatches")
@click.argument("palette_name")
@click.option("-o", "--output", "output_path", type=click.Path(dir_okay=False, path_type=Path),
              default=None, help="Output PNG (default: <palette>_swatches.png).")
@click.option("--cols", type=click.IntRange(1, 64), default=8, show_default=True)
@click.option("--size", "swatch", type=click.IntRange(8, 256), default=48, show_default=True,
              help="Swatch size in pixels.")
def swatches_cmd(palette_name: str, output_path: Optional[Path], cols: int, swatch: int) -> None:
    """Render a palette (name, .gpl/.hex file, or hw:MODE) as a swatch sheet."""
    if palette_name.lower().startswith("hw:"):
        try:
            mode = get_hardware_mode(palette_name[3:])
        except KeyError as exc:
            raise click.ClickException(str(exc.args[0])) from exc
        colors, title = list(mode.palette), mode.title
    else:
        try:
            colors, title = list(resolve_palette(palette_name)), palette_name
        except (KeyError, ValueError, OSError) as exc:
            raise click.ClickException(str(exc.args[0] if exc.args else exc)) from exc
    sheet = swatch_sheet(colors, cols=cols, swatch=swatch, title=f"{title} · {len(colors)} colors")
    if output_path is None:
        safe = Path(palette_name).stem.replace(":", "-")
        output_path = Path(f"{safe}_swatches.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    console.print(f"[bold green]✓[/bold green] Saved: [cyan]{output_path}[/cyan]  [dim]({sheet.size[0]}×{sheet.size[1]})[/dim]")
