"""PyInstaller entry point — absolute imports only, safe when frozen.

The package's __main__.py uses relative imports (python -m leadhound
semantics), which break under PyInstaller. This script is the build target.

Windows double-click hardening:
- stdout/stderr are reconfigured to UTF-8 so rich/emoji output never crashes
  a cp1252 console or a redirected pipe.
- Launched with no arguments (the double-click case), argparse would print
  "error: the following arguments are required: cmd" and the console window
  would vanish before anyone can read it. Instead we show a welcome screen
  and wait for Enter.
- Any unexpected crash prints the full traceback and waits for Enter, so the
  error can be read or screenshotted instead of flashing away.
"""

import contextlib
import sys

# UTF-8 everywhere before rich touches the console (cp1252-safe piping).
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _pause(prompt: str = "\nPress Enter to close...") -> None:
    """Hold the console window open; never raise."""
    with contextlib.suppress(EOFError, KeyboardInterrupt):
        input(prompt)


def _no_args_welcome() -> None:
    """Double-click launcher: explain how to actually use the CLI."""
    try:
        from rich.console import Console
        from rich.panel import Panel

        c = Console()
        c.print(Panel.fit(
            "[bold green]leadhound is a command-line tool.[/bold green]\n"
            "You launched it directly (double-click), so there is nothing to\n"
            "interact with here. Open a terminal in this folder instead and run:\n\n"
            "  [bold cyan].\\leadhound-windows-x64.exe init[/bold cyan]        one-time setup\n"
            "  [bold cyan].\\leadhound-windows-x64.exe doctor[/bold cyan]      verify everything works\n"
            "  [bold cyan].\\leadhound-windows-x64.exe demo[/bold cyan]        4 sample gigs, offline\n"
            "  [bold cyan].\\leadhound-windows-x64.exe queue[/bold cyan]       review them\n"
            "  [bold cyan].\\leadhound-windows-x64.exe web[/bold cyan]         dashboard in your browser\n\n"
            "[dim]Tip: rename the file to leadhound.exe and drop the .exe prefix\n"
            "from the commands above. Full guide: github.com/e2sy/leadhound[/dim]",
            title="🐺 leadhound",
            border_style="green",
        ))
    except Exception:
        print("leadhound — open a terminal and run: leadhound init | demo | queue | web")
    _pause()
    sys.exit(0)


def _crash_report(exc: BaseException) -> None:
    """Print a readable crash report and hold the window open (frozen only)."""
    print("\n--- leadhound crashed ---", file=sys.stderr)
    import traceback

    traceback.print_exc()
    print(
        "\nPlease screenshot this and open an issue:\n"
        "https://github.com/e2sy/leadhound/issues",
        file=sys.stderr,
    )
    if _is_frozen():
        _pause()


if __name__ == "__main__":
    if len(sys.argv) == 1 and _is_frozen():
        _no_args_welcome()
    try:
        from leadhound.cli import main

        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        pass
    except Exception:  # last-resort crash catcher, must not re-raise silently
        _crash_report(sys.exc_info()[1])
        sys.exit(1)
