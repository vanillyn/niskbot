from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.utils.ui import BaseLayout, PageBuilder, PaginatedLayout, paginate

if TYPE_CHECKING:
    from src.bot import Bot


_COMMANDS_PER_PAGE = 6


def _build_overview_page(
    categories: list[tuple[str, list[app_commands.Command[Any, Any, Any]]]],
) -> PageBuilder:
    def builder(layout: PaginatedLayout) -> None:
        layout.add_text("## help\nuse the arrows to browse commands by category.")
        layout.add_sep(large=True)
        lines: list[str] = []
        for name, cmds in categories:
            lines.append(f"**{name}** — {len(cmds)} command(s)")
        layout.add_text("\n".join(lines))

    return builder  # type: ignore[return-value]


def _build_category_page(
    category: str,
    cmds: list[app_commands.Command[Any, Any, Any]],
    chunk: list[app_commands.Command[Any, Any, Any]],
    page_num: int,
    total_pages: int,
) -> PageBuilder:
    def builder(layout: PaginatedLayout) -> None:
        header = f"## {category}"
        if total_pages > 1:
            header += f"  *(page {page_num}/{total_pages})*"
        layout.add_text(header)
        layout.add_sep(large=True)
        for cmd in chunk:
            desc = cmd.description or "no description"
            layout.add_text(f"**/{cmd.name}**\n{desc}")
            layout.add_sep()

    return builder  # type: ignore[return-value]


def _chunk(
    items: list[app_commands.Command[Any, Any, Any]], size: int
) -> list[list[app_commands.Command[Any, Any, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_pages(
    bot: Bot,
) -> list[PageBuilder]:
    raw = bot.tree.get_commands()

    categories: dict[str, list[app_commands.Command[Any, Any, Any]]] = {}
    for cmd in raw:
        if isinstance(cmd, app_commands.Command):
            cog_name = "misc"
            if cmd.binding is not None and isinstance(cmd.binding, commands.Cog):
                cog_name = cmd.binding.qualified_name.lower()
            categories.setdefault(cog_name, []).append(cmd)
        elif isinstance(cmd, app_commands.Group):
            group_name = cmd.name
            for sub in cmd.commands:
                if isinstance(sub, app_commands.Command):
                    categories.setdefault(group_name, []).append(sub)

    sorted_cats = sorted(categories.items())
    pages: list[PageBuilder] = [_build_overview_page(sorted_cats)]

    for cat_name, cmds in sorted_cats:
        chunks = _chunk(cmds, _COMMANDS_PER_PAGE)
        for i, chunk in enumerate(chunks):
            pages.append(
                _build_category_page(cat_name, cmds, chunk, i + 1, len(chunks))
            )

    return pages


class HelpCog(commands.Cog, name="help"):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="browse all available commands")
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        pages = _build_pages(self.bot)
        if not pages:
            await interaction.response.send_message(
                "no commands registered yet", ephemeral=True
            )
            return
        layout = paginate(pages)
        await interaction.response.send_message(view=layout, ephemeral=True)


async def setup(bot: Bot) -> None:
    await bot.add_cog(HelpCog(bot))
