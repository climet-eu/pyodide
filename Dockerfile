FROM pyodide/pyodide-env:20260211-chrome145-firefox146-py314

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
        flex \
  && rm -rf /var/lib/apt/lists/*

CMD ["/bin/sh"]
WORKDIR /src
