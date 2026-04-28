"""Retro CLI UI helpers built on Rich."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


BANNER = r"""
██████╗ ██╗██╗  ██╗███████╗██╗      █████╗ ████████╗███████╗
██╔══██╗██║╚██╗██╔╝██╔════╝██║     ██╔══██╗╚══██╔══╝██╔════╝
██████╔╝██║ ╚███╔╝ █████╗  ██║     ███████║   ██║   █████╗
██╔═══╝ ██║ ██╔██╗ ██╔══╝  ██║     ██╔══██║   ██║   ██╔══╝
██║     ██║██╔╝ ██╗███████╗███████╗██║  ██║   ██║   ███████╗
╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝
"""

TAGLINE = "  retro pixel art from any image  ·  v1.0.0"


def print_banner() -> None:
    """Print the PIXELATE banner with a retro CRT-green glow."""
    text = Text(BANNER, style="bold green")
    console.print(text)
    console.print(Text(TAGLINE, style="dim cyan"))
    console.print()


def print_palette_table(palettes: dict) -> None:
    """Render a table of available palettes."""
    table = Table(
        title="[bold cyan]Available Palettes[/bold cyan]",
        title_style="bold",
        border_style="green",
        header_style="bold magenta",
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Colors", style="yellow", justify="right")
    table.add_column("Vibe", style="white")

    vibes = {
        "gameboy": "Original DMG green-yellow",
        "gameboy-pocket": "Pocket / Light grayscale-green",
        "nes": "Nintendo Entertainment System",
        "c64": "Commodore 64",
        "zx": "ZX Spectrum",
        "cga": "MS-DOS CGA",
        "pico8": "PICO-8 fantasy console",
        "apple2": "Apple II low-res",
        "sunset": "Modern sunset gradient",
        "mono-green": "Phosphor green CRT",
        "mono-amber": "Amber CRT",
        "grayscale": "9-step grayscale",
    }

    for name, count in palettes.items():
        table.add_row(name, str(count), vibes.get(name, ""))
    console.print(table)


def info_panel(title: str, body: str) -> None:
    """Render a small info panel."""
    console.print(Panel(body, title=title, border_style="green", title_align="left"))
