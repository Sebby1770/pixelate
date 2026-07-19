"""Retro CLI UI helpers built on Rich."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pixelate import __version__

console = Console()


BANNER = r"""
██████╗ ██╗██╗  ██╗███████╗██╗      █████╗ ████████╗███████╗
██╔══██╗██║╚██╗██╔╝██╔════╝██║     ██╔══██╗╚══██╔══╝██╔════╝
██████╔╝██║ ╚███╔╝ █████╗  ██║     ███████║   ██║   █████╗
██╔═══╝ ██║ ██╔██╗ ██╔══╝  ██║     ██╔══██║   ██║   ██╔══╝
██║     ██║██╔╝ ██╗███████╗███████╗██║  ██║   ██║   ███████╗
╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝
"""


def print_banner() -> None:
    """Print the PIXELATE banner with a retro CRT-green glow."""
    text = Text(BANNER, style="bold green")
    console.print(text)
    tagline = f"  retro pixel art from any image  ·  v{__version__}"
    console.print(Text(tagline, style="dim cyan"))
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
        "gameboy-color": "Game Boy Color (32-color sample)",
        "gbc": "Game Boy Color (alias)",
        "nes": "Nintendo Entertainment System",
        "c64": "Commodore 64",
        "vic20": "Commodore VIC-20",
        "vic-20": "Commodore VIC-20 (alias)",
        "atari2600": "Atari 2600 TIA subset",
        "atari-2600": "Atari 2600 (alias)",
        "zx": "ZX Spectrum",
        "cga": "MS-DOS CGA",
        "pico8": "PICO-8 fantasy console",
        "apple2": "Apple II low-res",
        "sunset": "Modern sunset gradient",
        "mono-green": "Phosphor green CRT",
        "mono-amber": "Amber CRT",
        "grayscale": "9-step grayscale",
        "ega": "IBM EGA 16-color",
        "msx": "MSX Screen 2",
        "sms": "Sega Master System",
        "master-system": "Sega Master System (alias)",
        "db16": "DawnBringer 16",
        "vaporwave": "Aesthetic vaporwave",
        "tokyo-night": "Tokyo Night dark theme",
        "tokyo": "Tokyo Night (alias)",
        "cyberpunk": "Neon cyberpunk night",
    }

    for name, count in sorted(palettes.items()):
        table.add_row(name, str(count), vibes.get(name, ""))
    console.print(table)


def info_panel(title: str, body: str) -> None:
    """Render a small info panel."""
    console.print(Panel(body, title=title, border_style="green", title_align="left"))
