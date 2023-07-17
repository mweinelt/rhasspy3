#!/usr/bin/env python3
import argparse
import asyncio
import logging
from functools import partial
from pathlib import Path
from threading import Thread
from typing import Dict, List

from wyoming.info import Attribution, Info, WakeModel, WakeProgram
from wyoming.server import AsyncServer

from .handler import OpenWakeWordEventHandler
from .openwakeword import embeddings_proc, mels_proc, ww_proc
from .state import State, WakeWordState

_LOGGER = logging.getLogger()
_DIR = Path(__file__).parent


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True, help="unix:// or tcp://")
    parser.add_argument(
        "--model",
        required=True,
        action="append",
        help="Path to wake word model (.tflite)",
    )
    parser.add_argument(
        "--models-dir", default=_DIR / "models", help="Path to directory with models"
    )
    #
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    models_dir = Path(args.models_dir)
    model_paths: List[Path] = []
    for model in args.model:
        model_path = Path(model)
        if not model_path.exists():
            # Try relative to models dir
            model_path = models_dir / model

            if not model_path.exists():
                # Try with version + extension
                model_path = models_dir / f"{model}_v0.1.tflite"
                assert (
                    model_path.exists()
                ), f"Missing model: {model} (looked in: {models_dir.absolute()})"

        model_paths.append(model_path)

    wyoming_info = Info(
        wake=[
            WakeProgram(
                name="openwakeword",
                description="An open-source audio wake word (or phrase) detection framework with a focus on performance and simplicity.",
                attribution=Attribution(
                    name="dscripka", url="https://github.com/dscripka/openWakeWord"
                ),
                installed=True,
                models=[
                    WakeModel(
                        name=str(model_path),
                        description=model_path.stem,
                        attribution=Attribution(
                            name="dscripka",
                            url="https://github.com/dscripka/openWakeWord",
                        ),
                        installed=True,
                        languages=[],
                    )
                    for model_path in model_paths
                ],
            )
        ],
    )

    state = State(models_dir=models_dir)

    # One thread per wake word model
    loop = asyncio.get_running_loop()
    ww_threads: Dict[str, Thread] = {}
    for model_path in model_paths:
        model_key = str(model_path)
        state.wake_words[model_key] = WakeWordState()
        ww_threads[model_key] = Thread(
            # target=ww_proc_no_batch,
            target=ww_proc,
            daemon=True,
            args=(
                state,
                model_key,
                loop,
            ),
        )
        ww_threads[model_key].start()

    # audio -> mels
    mels_thread = Thread(target=mels_proc, daemon=True, args=(state,))
    mels_thread.start()

    # mels -> embeddings
    embeddings_thread = Thread(target=embeddings_proc, daemon=True, args=(state,))
    embeddings_thread.start()

    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info("Ready")

    try:
        await server.run(partial(OpenWakeWordEventHandler, wyoming_info, args, state))
    except KeyboardInterrupt:
        pass
    finally:
        # Graceful shutdown
        _LOGGER.debug("Shutting down")
        state.is_running = False
        state.audio_ready.release()
        mels_thread.join()

        state.mels_ready.release()
        embeddings_thread.join()

        for ww_name, ww_state in state.wake_words.items():
            ww_state.embeddings_ready.release()
            ww_threads[ww_name].join()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass