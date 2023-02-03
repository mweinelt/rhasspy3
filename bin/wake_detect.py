#!/usr/bin/env python3
"""Wait for wake word to be detected."""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from rhasspy3.core import Rhasspy
from rhasspy3.mic import DOMAIN as MIC_DOMAIN
from rhasspy3.program import create_process
from rhasspy3.wake import detect

_FILE = Path(__file__)
_DIR = _FILE.parent
_LOGGER = logging.getLogger(_FILE.stem)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        default=_DIR.parent / "config",
        help="Configuration directory",
    )
    parser.add_argument(
        "-p", "--pipeline", default="default", help="Name of pipeline to use"
    )
    parser.add_argument(
        "--mic-program", help="Name of mic program to use (overrides pipeline)"
    )
    parser.add_argument(
        "--wake-program", help="Name of wake program to use (overrides pipeline)"
    )
    #
    parser.add_argument(
        "--output-json", action="store_true", help="Outputs JSON instead of text"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to console"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    rhasspy = Rhasspy.load(args.config)
    mic_program = args.mic_program
    wake_program = args.wake_program
    pipeline = rhasspy.config.pipelines.get(args.pipeline)

    if not mic_program:
        assert pipeline is not None, f"No pipline named {args.pipeline}"
        mic_program = pipeline.mic

    assert mic_program, "No mic program"

    if not wake_program:
        assert pipeline is not None, f"No pipline named {args.pipeline}"
        wake_program = pipeline.wake

    assert wake_program, "No wake program"

    # Detect wake word
    async with (await create_process(rhasspy, MIC_DOMAIN, mic_program)) as mic_proc:
        assert mic_proc.stdout is not None
        detection = await detect(rhasspy, wake_program, mic_proc.stdout)
        if detection is not None:
            if args.output_json:
                json.dump(detection.event().data, sys.stdout)
                print("", flush=True)
            else:
                print(detection.name, flush=True)


if __name__ == "__main__":
    asyncio.run(main())