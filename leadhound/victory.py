"""The 'won' moment — a banner worth screenshotting for the timeline."""

from __future__ import annotations

from .db import Job

WOLF = r"""
      /\      /\
     { `---'  }
     {  O O  }
     ~~>  V <~~
      \  \|/  /
       `-----'__
       /     \  `^\_
      {       }\ |\_\_   W
      |  \_/  |/ /  \_\_( )
       \__/  /(_E     \__/
         (  /
          MM
"""


def gig_money(j: Job) -> str:
    if j.hourly:
        return f"${j.hourly:g}/hr"
    if j.budget_max:
        return f"${j.budget_max:,.0f}"
    if j.budget_min:
        return f"${j.budget_min:,.0f}+"
    return "budget not posted"


def build_victory_text(j: Job) -> str:
    """Plain-text victory card (rich renders it inside a green panel)."""
    return (
        WOLF
        + f"\n  GIG WON: {j.title}\n"
        + f"  Value:   {gig_money(j)}   Source: {j.source}\n"
        + f"  URL:     {j.url}\n\n"
        "  The scope pointed right. Log it, invoice it, keep shipping.\n"
    )
