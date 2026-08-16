#!/usr/bin/env python3
"""coffee-paladin as an iTerm2 status bar component.

Install: iTerm2 -> Scripts -> AutoLaunch -> save this file there (it needs
iTerm2's Python API runtime enabled), then add "Coffee Paladin" to the status
bar in Settings -> Profiles -> Session -> Status bar layout.

The component runs the same statusline script every 15 s and shows its first
line, colors stripped: iTerm2 renders status bar text itself, and the thermal
snapshot only refreshes every 15 s anyway. No paladin = empty component, never
an error badge.
"""
import asyncio
import os
import re

import iterm2

SCRIPT = os.path.expanduser("~/.coffee-paladin/statusline.sh")


async def main(connection):
    component = iterm2.StatusBarComponent(
        short_description="Coffee Paladin",
        detailed_description="coffee-paladin thermal guard state",
        knobs=[],
        exemplar="ON chip 55°",
        update_cadence=15,
        identifier="pl.pawel.coffee-paladin.statusbar")

    @iterm2.StatusBarRPC
    async def paladin_line(knobs):
        if not os.path.exists(SCRIPT):
            return ""
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash", SCRIPT,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=dict(os.environ, NO_COLOR="1",
                     COFFEE_PALADIN_STATUSLINE_ICONS="ascii"))
        out, _ = await proc.communicate()
        line = out.decode("utf-8", "replace").split("\n")[0]
        return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)

    await component.async_register(connection, paladin_line)


iterm2.run_forever(main)
