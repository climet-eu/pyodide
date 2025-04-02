import asyncio
import importlib
import sys

import js
import pyodide
import pyodide_js


def load_ipython_extension(ip):
    if getattr(load_ipython_extension, "_loaded", False):
        return
    load_ipython_extension._loaded = True

    patch_pyodide_stdio()

    if not pyodide.ffi.can_run_sync():
        patch_syncifiable_asyncio()

    patch_import_loader()

    # the import loader has been patched, so we can now sync-load pyodide-http
    import pyodide_http

    pyodide_http.patch_all()

    memory_monitor = PyodideMemoryMonitor()
    dynlib_monitor = PyodideDynlibMonitor()

    def pre_execute_hook(*args, **kwargs):
        try:
            js.__jupyterlite_preload_stream_write = sys.stdout.publish_stream_callback
        except AttributeError:
            pass

    def post_execute_hook(*args, **kwargs):
        memory_monitor.post_execute_hook()
        dynlib_monitor.post_execute_hook()

    ip.events.register("pre_execute", pre_execute_hook)
    ip.events.register("post_execute", post_execute_hook)


# patch some asyncio functions if JSPI is not available
def patch_syncifiable_asyncio():
    class AsCompletedIterator:
        def __init__(self, aws):
            self._aws = iter(aws)

        def __iter__(self):
            return self

        def __next__(self):
            return next(self._aws)

        def __aiter__(self):
            return self

        async def __anext__(self):
            return next(self._aws)

    def asyncio_as_completed(aws, *, timeout=None):
        return AsCompletedIterator(aws)

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

    async def asyncio_sleep(delay, result=None):
        import time

        time.sleep(delay)
        return result

    asyncio.as_completed = asyncio_as_completed
    asyncio.gather = asyncio_gather
    asyncio.sleep = asyncio_sleep


class PyodidePackageFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        # no need to load an already-imported package
        if fullname in sys.modules:
            return None

        # try to map the import fullname to a Pyodide package name
        package_name = None
        for name, package in js.Object.entries(pyodide_js.lockfile.packages):
            for import_name in package.imports:
                if import_name == fullname:
                    package_name = name
                    break
            if package_name is not None:
                break

        # we can only load packages in the Pyodide distribution
        if package_name is None:
            return None

        package = getattr(pyodide_js.lockfile.packages, package_name)

        # no need to load an already-loaded package
        if getattr(pyodide_js.loadedPackages, package.name, None) is not None:
            return None

        # use JSPI if available, otherwise fall back to loadPackageSync
        if pyodide.ffi.can_run_sync():
            pyodide.ffi.run_sync(pyodide_js.loadPackage(package_name))
        else:
            pyodide_js.loadPackageSync(package_name)

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
                return publish_stream_callback(stream, message);
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
            // "PACKAGE already loaded from CHANNEL"
            // messages
            if (message.includes(" already loaded from ")) {
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


class PyodideDynlibMonitor:
    def __init__(self):
        self.update()

    def update(self):
        self.dynlibs = js.Object.keys(
            pyodide_js._module.LDSO.loadedLibsByName,
        ).length

    def post_execute_hook(self):
        dynlibs_before = self.dynlibs
        self.update()
        dynlibs_after = self.dynlibs

        dynlibs_extra = dynlibs_after - dynlibs_before

        if dynlibs_extra > 0:
            print(
                f"[pyodide]: Loaded {dynlibs_extra} new dynamic "
                + f"librar{'ies' if dynlibs_extra > 1 else 'y'} "
                + f"({dynlibs_after} total for this notebook)",
            )
