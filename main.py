from __future__ import annotations

import asyncio

from dotenv import load_dotenv

from src.bot import main

load_dotenv()


asyncio.run(main())
