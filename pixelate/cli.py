"""Command-line interface for pixelate."""

from __future__ import annotations

from pathlib import Path

import click
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from pixelate import __version__
from pixelate.ascii_art import RAMPS, image_to_ascii, save_ascii
from pixelate.core import pixelate_image, save_image
from pixelate.dithering import DITHER_ALGORITHMS
from pixelate.palettes import PALETTES, list_palettes
from pixelate.ui import console, info_panel, print_banner, print_palette_table


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
    help="Output file path. Default: <input>_pixel.png",
)
@click.option(
    "-p", "--palette",
    type=click.Choice(list(PALETTES), case_sensitive=False),
    default="gameboy",
    show_default=True,
    help="Color palette to quantize toward.",
)
@click.option(
    "-s", "--pixel-size",
    type=click.IntRange(8, 1024),
    default=96,
    show_default=True,
    help='Resolution of longest side, in "logical" pixels.',
)
@click.option(
    "-d", "--dither",
    type=click.Choice(list(DITHER_ALGORITHMS), case_sensitive=False),
    default="floyd",
    show_default=True,
    help="Dithering algorithm.",
)
@click.option(
    "-u", "--upscale",
    type=click.IntRange(1, 16),
    default=4,
    show_default=True,
    help="How many output pixels per logical pixel.",
)
@click.option(
    "--saturation",
    type=click.FloatRange(0.0, 3.0),
    default=1.2,
    show_default=True,
    help="Saturation boost applied before quantization.",
)
@click.option("--crt", is_flag=True, help="Apply CRT glow + vignette.")
@click.option("--scanlines", is_flag=True, help="Overlay horizontal scanlines.")
def convert_cmd(
    input_path: Path,
    output_path: Path | None,
    palette: str,
    pixel_size: int,
    dither: str,
    upscale: int,
    saturation: float,
    crt: bool,
    scanlines: bool,
) -> None:
    """Convert IMAGE to retro pixel art."""
    print_banner()

    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_pixel.png")

    info_panel(
        "[bold]Converting[/bold]",
        (
            f"[cyan]Source:[/cyan]    {input_path}\n"
            f"[cyan]Palette:[/cyan]   [yellow]{palette}[/yellow] "
            f"({len(PALETTES[palette])} colors)\n"
            f"[cyan]Resolution:[/cyan] {pixel_size}px (longest side) × {upscale}× upscale\n"
            f"[cyan]Dither:[/cyan]    {dither}\n"
            f"[cyan]Effects:[/cyan]   "
            f"{'CRT ' if crt else ''}{'scanlines' if scanlines else ('none' if not crt else '')}"
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
        try:
            result = pixelate_image(
                input_path,
                palette=palette,
                pixel_size=pixel_size,
                dither=dither,
                upscale=upscale,
                saturation=saturation,
                crt=crt,
                scanlines=scanlines,
            )
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        progress.update(task, completed=1, total=1)

    saved = save_image(result, output_path)
    console.print(f"[bold green]✓[/bold green] Saved: [cyan]{saved}[/cyan]  "
                  f"[dim]({result.size[0]}×{result.size[1]})[/dim]")


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
    try:
        art = image_to_ascii(
            input_path,
            width=width,
            ramp=ramp,
            color=color,
            invert=invert,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(art)
    if output_path:
        saved = save_ascii(art, output_path)
        console.print(f"\n[bold green]✓[/bold green] Saved: [cyan]{saved}[/cyan]")


@cli.command("palettes")
def palettes_cmd() -> None:
    """List all built-in palettes."""
    print_banner()
    print_palette_table(list_palettes())


@cli.command("preview")
@click.argument("palette_name", type=click.Choice(list(PALETTES), case_sensitive=False))
def preview_cmd(palette_name: str) -> None:
    """Print a swatch of a palette in your terminal."""
    from pixelate.palettes import get_palette
    palette = get_palette(palette_name)
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
