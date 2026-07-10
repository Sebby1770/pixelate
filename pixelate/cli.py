"""Command-line interface for pixelate."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from pixelate import __version__
from pixelate.animation import is_animated, pixelate_animation
from pixelate.ascii_art import RAMPS, image_to_ascii, save_ascii
from pixelate.core import (
    collect_images,
    make_spritesheet,
    pixelate_image,
    resolve_palette,
    save_image,
)
from pixelate.dithering import DITHER_ALGORITHMS
from pixelate.palette_io import load_palette_file, register_palette
from pixelate.palettes import PALETTES, list_palettes
from pixelate.ui import console, info_panel, print_banner, print_palette_table


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
            help="Built-in palette name (ignored if --palette-file is set).",
        ),
        click.option(
            "--palette-file",
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            default=None,
            help="Custom palette file (.hex or .gpl).",
        ),
        click.option(
            "-s", "--pixel-size",
            type=click.IntRange(8, 1024),
            default=96,
            show_default=True,
            help='Resolution of longest side, in "logical" pixels.',
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
            "--saturation",
            type=click.FloatRange(0.0, 3.0),
            default=1.2,
            show_default=True,
            help="Saturation boost applied before quantization.",
        ),
        click.option("--crt", is_flag=True, help="Apply CRT glow + vignette."),
        click.option("--scanlines", is_flag=True, help="Overlay horizontal scanlines."),
    ]
    for opt in reversed(options):
        fn = opt(fn)
    return fn


def _validate_palette_name(palette: str, palette_file: Optional[Path]) -> None:
    if palette_file is not None:
        return
    # Allow path-as-palette or registered name
    p = Path(palette)
    if p.is_file():
        return
    if palette.lower().strip() not in PALETTES:
        available = ", ".join(sorted(PALETTES))
        raise click.ClickException(
            f"Unknown palette '{palette}'. Available: {available}\n"
            "Or pass a .hex/.gpl file with --palette-file."
        )


def _palette_label(palette: str, palette_file: Optional[Path]) -> str:
    if palette_file is not None:
        colors = load_palette_file(palette_file)
        return f"file:{palette_file.name} ({len(colors)} colors)"
    try:
        colors = resolve_palette(palette)
        return f"{palette} ({len(colors)} colors)"
    except Exception:
        return palette


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
    pixel_size: int,
    dither: str,
    upscale: int,
    saturation: float,
    crt: bool,
    scanlines: bool,
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
    effects_str = " ".join(effects) if effects else "none"

    info_panel(
        "[bold]Converting[/bold]",
        (
            f"[cyan]Source:[/cyan]    {input_path}\n"
            f"[cyan]Palette:[/cyan]   [yellow]{_palette_label(palette, palette_file)}[/yellow]\n"
            f"[cyan]Resolution:[/cyan] {pixel_size}px (longest side) × {upscale}× upscale\n"
            f"[cyan]Dither:[/cyan]    {dither}\n"
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
            result = pixelate_animation(
                input_path,
                palette=palette,
                pixel_size=pixel_size,
                dither=dither,
                upscale=upscale,
                saturation=saturation,
                crt=crt,
                scanlines=scanlines,
                palette_file=palette_file,
                output=output_path,
            )
            # result is first frame Image when output is set
            size_label = f"{result.size[0]}×{result.size[1]}"
            saved = output_path
        else:
            result = pixelate_image(
                input_path,
                palette=palette,
                pixel_size=pixel_size,
                dither=dither,
                upscale=upscale,
                saturation=saturation,
                crt=crt,
                scanlines=scanlines,
                palette_file=palette_file,
            )
            saved = save_image(result, output_path)
            size_label = f"{result.size[0]}×{result.size[1]}"
        progress.update(task, completed=1, total=1)

    console.print(
        f"[bold green]✓[/bold green] Saved: [cyan]{saved}[/cyan]  "
        f"[dim]({size_label}{' animated' if animated else ''})[/dim]"
    )


@cli.command("batch")
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "-o", "--output", "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    required=True,
    help="Directory for converted images.",
)
@click.option("--recursive", "-r", is_flag=True, help="Scan subdirectories.")
@_common_convert_options
def batch_cmd(
    input_dir: Path,
    output_dir: Path,
    recursive: bool,
    palette: str,
    palette_file: Path | None,
    pixel_size: int,
    dither: str,
    upscale: int,
    saturation: float,
    crt: bool,
    scanlines: bool,
) -> None:
    """Batch-convert all images in INPUT_DIR into OUTPUT_DIR."""
    print_banner()
    _validate_palette_name(palette, palette_file)

    images = collect_images([input_dir], recursive=recursive)
    if not images:
        raise click.ClickException(f"No images found in {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    info_panel(
        "[bold]Batch convert[/bold]",
        (
            f"[cyan]Input:[/cyan]     {input_dir}\n"
            f"[cyan]Output:[/cyan]    {output_dir}\n"
            f"[cyan]Images:[/cyan]    {len(images)}\n"
            f"[cyan]Palette:[/cyan]   [yellow]{_palette_label(palette, palette_file)}[/yellow]\n"
            f"[cyan]Dither:[/cyan]    {dither}"
        ),
    )

    ok = 0
    errors: list[str] = []

    with Progress(
        SpinnerColumn(style="green"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="green", finished_style="bright_green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Converting...", total=len(images))
        for src in images:
            rel = src.relative_to(input_dir) if src.is_relative_to(input_dir) else src.name
            out_name = Path(rel).stem + "_pixel"
            try:
                if is_animated(src):
                    dest = output_dir / Path(rel).with_name(out_name + ".gif")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    pixelate_animation(
                        src,
                        palette=palette,
                        pixel_size=pixel_size,
                        dither=dither,
                        upscale=upscale,
                        saturation=saturation,
                        crt=crt,
                        scanlines=scanlines,
                        palette_file=palette_file,
                        output=dest,
                    )
                else:
                    dest = output_dir / Path(rel).with_name(out_name + src.suffix.lower())
                    if dest.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                        dest = dest.with_suffix(".png")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    result = pixelate_image(
                        src,
                        palette=palette,
                        pixel_size=pixel_size,
                        dither=dither,
                        upscale=upscale,
                        saturation=saturation,
                        crt=crt,
                        scanlines=scanlines,
                        palette_file=palette_file,
                    )
                    save_image(result, dest)
                ok += 1
            except Exception as exc:  # noqa: BLE001 — report and continue batch
                errors.append(f"{src.name}: {exc}")
            progress.advance(task)

    console.print(f"[bold green]✓[/bold green] Converted {ok}/{len(images)} images → [cyan]{output_dir}[/cyan]")
    for err in errors:
        console.print(f"[bold red]✗[/bold red] {err}")


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
    pixel_size: int,
    dither: str,
    upscale: int,
    saturation: float,
    crt: bool,
    scanlines: bool,
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

    info_panel(
        "[bold]Spritesheet[/bold]",
        (
            f"[cyan]Inputs:[/cyan]    {len(files)} images\n"
            f"[cyan]Columns:[/cyan]   {cols}\n"
            f"[cyan]Convert:[/cyan]   {'yes' if convert else 'no (stitch as-is)'}\n"
            f"[cyan]Palette:[/cyan]   [yellow]{_palette_label(palette, palette_file)}[/yellow]\n"
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
        from PIL import Image

        for src in files:
            if convert:
                tile = pixelate_image(
                    src,
                    palette=palette,
                    pixel_size=pixel_size,
                    dither=dither,
                    upscale=upscale,
                    saturation=saturation,
                    crt=crt,
                    scanlines=scanlines,
                    palette_file=palette_file,
                )
            else:
                tile = Image.open(src).convert("RGB")
            tiles.append(tile)
            progress.advance(task)

    sheet = make_spritesheet(tiles, cols=cols, padding=padding)
    saved = save_image(sheet, output_path)
    console.print(
        f"[bold green]✓[/bold green] Spritesheet: [cyan]{saved}[/cyan]  "
        f"[dim]({sheet.size[0]}×{sheet.size[1]}, {len(tiles)} tiles)[/dim]"
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
def palettes_cmd(load_file: Path | None, register_as: str | None) -> None:
    """List all built-in palettes (optionally load a custom file)."""
    print_banner()

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
