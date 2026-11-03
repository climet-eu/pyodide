FROM pyodide/pyodide-env:20260211-chrome145-firefox146-py314

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
        flex \
  && rm -rf /var/lib/apt/lists/*

ADD requirements.txt /

WORKDIR /
RUN pip3 --no-cache-dir install -r --upgrade requirements.txt \
    && rm requirements.txt

CMD ["/bin/sh"]
WORKDIR /src
