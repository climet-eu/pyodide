import logging


def load_ipython_extension(ip):
    print("hello")

    logging.debug("hi")

    raise RuntimeError("Error!")
