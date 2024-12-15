import asyncio
import importlib
import sys
from pathlib import Path

import js
import pyodide
import pyodide_js

import ipyloglite

import pyodide_http


def patch_syncifiable_asyncio():
    async def asyncio_gather(*coros_or_futures, return_exceptions=False):
        results = []

        for coro in coros_or_futures:
            try:
                results.append(await coro)
            except Exception as err:
                if return_exceptions:
                    results.append(err)
                else:
                    raise

        return results

    # FIXME: somehow detect if we're actually running on a loop and use the
    #        actual async sleep in that case
    async def asyncio_sleep(delay, result=None):
        import time

        time.sleep(delay)
        return result

    asyncio.gather = asyncio_gather
    asyncio.sleep = asyncio_sleep


def patch_pyodide_stdio():
    pyodide.code.run_js(r"""
        function jupyterLiteStreamWrite(stream, message) {
            if (this.__jupyterlite_preload_stream_callback === undefined) {
                this.__jupyterlite_preload_stream_callback =
                    this.__jupyterlite_preload_pyodide.runPython(
                        "import pyodide_kernel;" +
                        "pyodide_kernel.sys.stdout.publish_stream_callback"
                    );
                delete this.__jupyterlite_preload_pyodide;
            }
            this.__jupyterlite_preload_stream_callback(stream, message);
        }
        this.__jupyterlite_preload_stream_write = jupyterLiteStreamWrite;
    """)

    js.__jupyterlite_preload_pyodide = pyodide_js

    pyodideStdout = pyodide.code.run_js(r"""
        function pyodideStdout(message) {
            this.__jupyterlite_preload_stream_write(
                "stdout", "[pyodide]: " + message + "\n",
            );
        }
        { batched: pyodideStdout }
    """)
    pyodideStderr = pyodide.code.run_js(r"""
        function pyodideStderr(message) {
            this.__jupyterlite_preload_stream_write(
                "stderr", "[pyodide]: " + message + "\n",
            );
        }
        { batched: pyodideStderr }
    """)

    pyodide_js.setStdout(pyodideStdout)
    pyodide_js.setStderr(pyodideStderr)


def patch_pyodide_load_package():
    loadPackageMessage = pyodide.code.run_js(r"""
        function loadPackageMessage(message) {
            // Reduce noise by ignoring
            // "PACKAGE already loaded from CHANNEL channel"
            // messages
            if (
                message.includes(" already loaded from ") &&
                message.endsWith(" channel")
            ) {
                return;
            }

            // Reduce noise by ignoring "No new packages to load" messages
            if (message === "No new packages to load") {
                return;
            }

            this.__jupyterlite_preload_stream_write(
                "stdout", "[micropip]: " + message + "\n",
            );
        }
        loadPackageMessage
    """)
    loadPackageError = pyodide.code.run_js(r"""
        function loadPackageError(message) {
            this.__jupyterlite_preload_stream_write(
                "stderr", "[micropip]: " + message + "\n",
            );
        }
        loadPackageError
    """)

    _loadPackage = pyodide_js.loadPackage

    async def loadPackage(names, options=None):
        if options is None:
            options = js.Object.new()

        if getattr(options, "messageCallback", None) is None:
            options.messageCallback = loadPackageMessage
        if getattr(options, "errorCallback", None) is None:
            options.errorCallback = loadPackageError
        if getattr(options, "checkIntegrity", None) is None:
            options.checkIntegrity = True

        return await _loadPackage(names, options)

    pyodide_js.loadPackage = loadPackage

    async def loadPackagesFromImports(
        code: str,
        options=None,
    ):
        if options is None:
            options = js.Object.new()

        imports = set()

        for name in pyodide.code.find_imports(code):
            if name in sys.modules:
                continue

            try:
                spec = importlib.util.find_spec(name)
            except ModuleNotFoundError:
                spec = None
            if spec is not None and Path(spec.origin).parts[:2] == (
                "/",
                "drive",
            ):
                with open(spec.origin, "r") as f:
                    await loadPackagesFromImports(f.read(), options=options)

            if name in pyodide_js._api._import_name_to_package_name:
                imports.add(pyodide_js._api._import_name_to_package_name[name])

        return await loadPackage(list(imports), options=options)

    pyodide_js.loadPackagesFromImports = loadPackagesFromImports


def patch_all():
    if getattr(patch_all, "_patched", False):
        return
    patch_all._patched = True

    pyodide_http.patch_all()

    patch_syncifiable_asyncio()
    patch_pyodide_stdio()
    patch_pyodide_load_package()


class PyodideMemoryMonitor:
    def __init__(self):
        self.update()

    def update(self):
        self.memory = pyodide_js._module.HEAPU8.length

    # https://stackoverflow.com/a/1094933
    def sizeof_fmt(self, num, suffix="B"):
        for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Yi{suffix}"

    def post_execute_hook(self, *args, **kwargs):
        memory_before = self.sizeof_fmt(self.memory)
        self.update()
        memory_after = self.sizeof_fmt(self.memory)

        if memory_after != memory_before:
            print(
                f"[pyodide]: Memory usage has grown to {memory_after} "
                + f"(from {memory_before}) for this notebook",
                file=sys.stderr if self.memory > 2**30 else sys.stdout,
            )


patch_all()


def _finalize_with_ipython(ip):
    monitor = PyodideMemoryMonitor()
    ip.events.register("post_execute", monitor.post_execute_hook)
