import sys

import js

CORS_URL = "https://cors.climet.eu/"

# allow same-origin and CORS proxy requests without extra proxying
cors_origins = {js.location.origin: True, js.URL.new(CORS_URL).origin: True}


def cors_url(url: str) -> str:
    url_origin = js.URL.new(url).origin

    if cors_origins.get(url_origin, None) is None:
        # try HEAD first but fall back to GET if it's unsupported
        for method in ["HEAD", "GET"]:
            xhr = js.XMLHttpRequest.new()
            xhr.responseType = "arraybuffer"
            xhr.open(method, url, False)

            try:
                xhr.send()
            except Exception:
                # CORS preflight might have raised an exception
                cors_origins[url_origin] = False
                break
            else:
                if xhr.status >= 200 and xhr.status <= 399:
                    # request succeeded
                    cors_origins[url_origin] = True
                    break
                if xhr.status == 403:  # forbidden
                    # CORS preflight request might return FORBIDDEN
                    cors_origins[url_origin] = False
                    break

        # print a warning when CORS proxying is first enabled for an origin
        if cors_origins.get(url_origin, None) is False:
            print(
                f"""
[CORS]: The origin {url_origin} does not support Cross-Origin Resource Sharing.
        Requests to this origin are being proxied, which may reduce performance.

        Please ask the maintainers of {url_origin} to enable CORS using the
        Access-Control-Allow-Origin header.

        Please see https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS for
        more information about Cross-Origin Resource Sharing.
""".strip(),
                file=sys.stderr,
            )

    # proxy requests if necessary
    if cors_origins.get(url_origin, None) is False:
        url = f"https://cors.climet.eu/{url}"

    return url


def cors_status(url: str, status: int) -> int:
    url_origin = js.URL.new(url).origin

    if not cors_origins.get(url_origin, True):
        # redirect codes 301, 302, 303, 307, and 308 are hidden in 2xx codes by
        #  the proxy since browsers follow redirects automatically
        if status in [251, 252, 253, 257, 258]:
            return status + 50

    return status
