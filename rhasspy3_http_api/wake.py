import argparse
import asyncio
import logging

from quart import request, Quart

from rhasspy3.core import Rhasspy
from rhasspy3.config import PipelineConfig
from rhasspy3.mic import DOMAIN as MIC_DOMAIN
from rhasspy3.program import create_process
from rhasspy3.wake import detect

_LOGGER = logging.getLogger(__name__)


def add_wake(
    app: Quart, rhasspy: Rhasspy, pipeline: PipelineConfig, args: argparse.Namespace
) -> None:
    @app.route("/api/wait-for-wake", methods=["GET", "POST"])
    async def api_wait_for_wake() -> str:
        mic_program = request.args.get("mic_program", pipeline.mic)
        wake_program = request.args.get("wake_program", pipeline.wake)

        _LOGGER.debug("wait-for-wake: mic=%s, wake=%s", mic_program, wake_program)

        name = ""
        mic_proc = await create_process(rhasspy, MIC_DOMAIN, mic_program)
        try:
            assert mic_proc.stdout is not None
            result = await detect(rhasspy, wake_program, mic_proc.stdout)
            _LOGGER.debug("wait-for-wake: detect=%s", result)
            if result is not None:
                name = result.name or ""
        finally:
            mic_proc.terminate()
            asyncio.create_task(mic_proc.wait())

        return name
