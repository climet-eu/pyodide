import asyncio
import importlib
import sys
from pathlib import Path

import pyodide
import pyodide_js

import ipyloglite

import pyodide_http
pyodide_http.patch_all()


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


# FIXME: somehow detect if we're actually running on a loop and use the actual
#        async sleep in that case
async def asyncio_sleep(delay, result=None):
    import time
    time.sleep(delay)
    return result


asyncio.gather = asyncio_gather
asyncio.sleep = asyncio_sleep


async def loadPackagesFromImports(
    code: str, options=dict(checkIntegrity=True),
):
    imports = set()

    for name in pyodide.code.find_imports(code):
        if name in sys.modules:
            continue

        spec = importlib.util.find_spec(name)
        if spec is not None and Path(spec.origin).parts[:2] == (
            "/", "drive",
        ):
            with open(spec.origin, "r") as f:
                await loadPackagesFromImports(f.read(), options=options)

        if name in pyodide_js._api._import_name_to_package_name:
            imports.add(
                pyodide_js._api._import_name_to_package_name[name]
            )

    return await pyodide_js.loadPackage(list(imports))


pyodide_js.loadPackagesFromImports = loadPackagesFromImports
