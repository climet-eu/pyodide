import ctypes as _ctypes
import shlex as _shlex
import sys as _sys

from pathlib import Path as _Path
from tempfile import TemporaryFile as _TemporaryFile


_dll = _ctypes.CDLL(_Path(__file__).parent / "libgit2.so")


def git(*args: list[str]):
    argc = len(args) + 1

    argv = (_ctypes.c_char_p * argc)()
    argv[0] = "git".encode("utf-8")
    argv[1:] = [a.encode("utf-8") for a in args]

    with _TemporaryFile() as out, _TemporaryFile() as err:
        status = _dll.git_main(argc, argv, out.fileno(), err.fileno())

        out.seek(0); out = out.read().decode("utf-8").rstrip()
        err.seek(0); err = err.read().decode("utf-8").rstrip()
    
    if len(out) > 0:
        print(out, end="", file=_sys.stdout, flush=True)
    if len(err) > 0:
        print(err, end="", file=_sys.stderr, flush=True)


try:
    from IPython.core.magic import register_line_magic as _register_line_magic
except ModuleNotFoundError:
    pass
else:
    @_register_line_magic("git")
    def _git_magic(line):
        git(*_shlex.split(line))
