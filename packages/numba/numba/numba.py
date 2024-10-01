# Inspired by https://github.com/librosa/librosa/issues/1854#issuecomment-2223224746

import sys
from unittest.mock import MagicMock

import numpy as np


# mock the @jit @njit decorators as a no-op
def jit(*args, **kwargs):
    if len(args) == 1 and callable(args[0]):
        return args[0]  # @jit / @njit without arguments
    else:
        def wrapper(func):
            return func  # @jit / @njit with arguments

        return wrapper


# mock the @vectorize decorator using numpy
def vectorize(*args, **kwargs):
    if len(args) == 1 and callable(args[0]):
        return np.vectorize(args[0])  # @vectorize without arguments
    else:
        def wrapper(func):
            return np.vectorize(func)  # @vectorize with arguments

        return wrapper


# mock the @guvectorize decorator using numpy
def guvectorize(signatures, layout, *args, **kwargs):
    def wrapper(func):
        return np.vectorize(func, signature=layout)  # @guvectorize

    return wrapper


# create a mock numba module
numba = MagicMock()

numba.jit = jit
numba.njit = jit
numba.vectorize = vectorize
numba.guvectorize = guvectorize

# replace this module with the mock
sys.modules[__name__] = numba
