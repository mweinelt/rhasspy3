import asyncio
import logging
import os
import shlex
import string
from asyncio.subprocess import PIPE, Process
from typing import Optional, Union

from .config import CommandConfig, PipelineProgramConfig, ProgramConfig
from .core import Rhasspy
from .util import merge_dict

_LOGGER = logging.getLogger(__name__)


class MissingProgramConfigError(Exception):
    pass


class ProcessContextManager:
    def __init__(self, proc: Process, name: str):
        self.proc = proc
        self.name = name

    async def __aenter__(self):
        return self.proc

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self.proc.returncode is None:
                self.proc.terminate()
                await self.proc.wait()
        except ProcessLookupError:
            # Expected when process has already exited
            pass
        except Exception:
            _LOGGER.exception("Unexpected error stopping process: %s", self.name)


async def create_process(
    rhasspy: Rhasspy, domain: str, name: Union[str, PipelineProgramConfig]
) -> ProcessContextManager:
    pipeline_config: Optional[PipelineProgramConfig] = None
    if isinstance(name, PipelineProgramConfig):
        pipeline_config = name
        name = pipeline_config.name

    assert name, f"No program name for domain {domain}"

    if "." in name:
        base_name = name.split(".", maxsplit=1)[0]
    else:
        base_name = name

    program_config: Optional[ProgramConfig] = rhasspy.config.programs.get(
        domain, {}
    ).get(name)
    assert program_config is not None, f"No config for program {domain}/{name}"
    assert isinstance(program_config, ProgramConfig)

    command_str = program_config.command.strip()
    mapping = program_config.template_args or {}

    if pipeline_config is not None:
        if pipeline_config.template_args:
            merge_dict(mapping, pipeline_config.template_args)

    if mapping:
        command_template = string.Template(command_str)
        command_str = command_template.safe_substitute(mapping)

    working_dir = rhasspy.config_dir / "programs" / domain / base_name
    env = dict(os.environ)

    # Add rhasspy3/bin to $PATH
    env["PATH"] = f'{rhasspy.base_dir}/bin:${env["PATH"]}'

    # Ensure stdout is flushed for Python programs
    env["PYTHONUNBUFFERED"] = "1"

    cwd = working_dir if working_dir.is_dir() else None

    if program_config.shell:
        if program_config.adapter:
            program, *args = shlex.split(program_config.adapter)
            args.append("--shell")
            args.append(command_str)

            proc = await asyncio.create_subprocess_exec(
                program,
                *args,
                stdin=PIPE,
                stdout=PIPE,
                cwd=cwd,
                env=env,
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                command_str,
                stdin=PIPE,
                stdout=PIPE,
                cwd=cwd,
                env=env,
            )
    else:
        if program_config.adapter:
            program, *args = shlex.split(program_config.adapter)
            args.append(command_str)
        else:
            program, *args = shlex.split(command_str)

        proc = await asyncio.create_subprocess_exec(
            program,
            *args,
            stdin=PIPE,
            stdout=PIPE,
            cwd=cwd,
            env=env,
        )

    return ProcessContextManager(proc, name=name)


async def run_command(rhasspy: Rhasspy, command_config: CommandConfig) -> int:
    env = dict(os.environ)

    # Add rhasspy3/bin to $PATH
    env["PATH"] = f'{rhasspy.base_dir}/bin:${env["PATH"]}'

    # Ensure stdout is flushed for Python programs
    env["PYTHONUNBUFFERED"] = "1"

    if command_config.shell:
        proc = await asyncio.create_subprocess_shell(
            command_config.command,
            env=env,
        )
    else:
        program, *args = shlex.split(command_config.command)
        proc = await asyncio.create_subprocess_exec(
            program,
            *args,
            env=env,
        )

    await proc.wait()
    assert proc.returncode is not None

    return proc.returncode
