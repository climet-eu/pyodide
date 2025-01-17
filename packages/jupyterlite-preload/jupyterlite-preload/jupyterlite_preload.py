import asyncio
import importlib
import sys

import js
import pyodide
import pyodide_js

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


class PyodidePackageFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        # no need to load an already-imported package
        if fullname in sys.modules:
            return None

        # we can only load packages in the Pyodide distribution
        if fullname not in pyodide_js._api._import_name_to_package_name:
            return None

        package_name = pyodide_js._api._import_name_to_package_name[fullname]

        # no need to load an already-loaded package
        if getattr(pyodide_js.loadedPackages, package_name, None) is not None:
            return None

        # we only load the package itself
        # its dependencies will be loaded lazily on import as well
        options = js.Object.new()
        options.checkIntegrity = True
        options.loadPackageDependencies = False

        pyodide_js.loadPackageSync(package_name, options)

        # the package is now installed and can be loaded as usual
        return None


def patch_import_loader():
    sys.meta_path.insert(0, PyodidePackageFinder())


def patch_pyodide_stdio():
    pyodide.code.run_js(r"""
        function jupyterLiteStreamWrite(stream, message) {
            let publish_stream_callback = undefined;
            try {
                publish_stream_callback = self.__jupyterlite_preload_pyodide.runPython(
                    "import sys; sys.stdout.publish_stream_callback",
                );
            } catch {}

            if (publish_stream_callback !== undefined) {
                self.__jupyterlite_preload_stream_write = publish_stream_callback;
                delete self.__jupyterlite_preload_pyodide;
            }
        }
        self.__jupyterlite_preload_stream_write = jupyterLiteStreamWrite;
    """)

    js.__jupyterlite_preload_pyodide = pyodide_js

    pyodideStdout = pyodide.code.run_js(r"""
        function pyodideStdout(message) {
            console.log(message);

            self.__jupyterlite_preload_stream_write(
                "stdout", "[pyodide]: " + message + "\n",
            );
        }
        { batched: pyodideStdout }
    """)
    pyodideStderr = pyodide.code.run_js(r"""
        function pyodideStderr(message) {
            console.error(message);

            self.__jupyterlite_preload_stream_write(
                "stderr", "[pyodide]: " + message + "\n",
            );
        }
        { batched: pyodideStderr }
    """)

    pyodide_js.setStdout(pyodideStdout)
    pyodide_js.setStderr(pyodideStderr)

    loadPackageStdout = pyodide.code.run_js(r"""
        function loadPackageStdout(message) {
            console.log(message);

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

            self.__jupyterlite_preload_stream_write(
                "stdout", "[pyodide]: " + message + "\n",
            );
        }
        loadPackageStdout
    """)
    loadPackageStderr = pyodide.code.run_js(r"""
        function loadPackageStderr(message) {
            console.error(message);

            self.__jupyterlite_preload_stream_write(
                "stderr", "[pyodide]: " + message + "\n",
            );
        }
        loadPackageStderr
    """)

    pyodide_js.loadPackageSetStdout(loadPackageStdout)
    pyodide_js.loadPackageSetStderr(loadPackageStderr)


def patch_all():
    if getattr(patch_all, "_patched", False):
        return
    patch_all._patched = True

    pyodide_http.patch_all()

    patch_syncifiable_asyncio()
    patch_import_loader()
    patch_pyodide_stdio()


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

    def post_execute_hook(self):
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


    def pre_execute_hook(*args, **kwargs):
        try:
            js.__jupyterlite_preload_stream_write = sys.stdout.publish_stream_callback
        except AttributeError:
            pass


    def post_execute_hook(*args, **kwargs):
        monitor.post_execute_hook()


    ip.events.register("pre_execute", pre_execute_hook)
    ip.events.register("post_execute", post_execute_hook)
