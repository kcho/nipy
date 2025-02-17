from __future__ import absolute_import

import numpy as np

from scipy.stats import norm
import scipy.linalg as spl


from ..utils import (multiple_mahalanobis, z_score, multiple_fast_inv,
                     check_cast_bin8)
from nose.tools import assert_true, assert_equal, assert_raises
from numpy.testing import (assert_almost_equal, assert_array_almost_equal,
                           assert_array_equal)


def test_z_score():
    p = np.random.rand(10)
    z = z_score(p)
    assert_array_almost_equal(norm.sf(z), p)


def test_mahalanobis():
    x = np.random.rand(100) / 100
    A = np.random.rand(100, 100) / 100
    A = np.dot(A.transpose(), A) + np.eye(100)
    mah = np.dot(x, np.dot(np.linalg.inv(A), x))
    assert_almost_equal(mah, multiple_mahalanobis(x, A), decimal=1)


def test_mahalanobis2():
    x = np.random.randn(100, 3)
    Aa = np.zeros([100, 100, 3])
    for i in range(3):
        A = np.random.randn(120, 100)
        A = np.dot(A.T, A)
        Aa[:, :, i] = A
    i = np.random.randint(3)
    mah = np.dot(x[:, i], np.dot(np.linalg.inv(Aa[:, :, i]), x[:, i]))
    f_mah = (multiple_mahalanobis(x, Aa))[i]
    assert_almost_equal(mah, f_mah)


def test_multiple_fast_inv():
    shape = (10, 20, 20)
    X = np.random.randn(*shape)
    X_inv_ref = np.zeros(shape)
    for i in range(shape[0]):
        X[i] = np.dot(X[i], X[i].T)
        X_inv_ref[i] = spl.inv(X[i])
    X_inv = multiple_fast_inv(X)
    assert_array_almost_equal(X_inv_ref, X_inv)


def assert_equal_bin8(actual, expected):
    res = check_cast_bin8(actual)
    assert_equal(res.shape, actual.shape)
    assert_true(res.dtype.type == np.uint8)
    assert_array_equal(res, expected)


def test_check_cast_bin8():
    # Function to return np.uint8 array with check whether array is binary.
    for in_dtype in np.sctypes['int'] + np.sctypes['uint']:
        assert_equal_bin8(np.array([0, 1, 1, 1], in_dtype), [0, 1, 1, 1])
        assert_equal_bin8(np.array([[0, 1], [1, 1]], in_dtype),
                          [[0, 1], [1, 1]])
        assert_raises(ValueError, check_cast_bin8,
                      np.array([0, 1, 2], dtype=in_dtype))
    for in_dtype in np.sctypes['float']:
        assert_equal_bin8(np.array([0, 1, 1, -0], np.float), [0, 1, 1, 0])
        assert_equal_bin8(np.array([[0, 1], [1, -0]], np.float),
                          [[0, 1], [1, 0]])
        assert_raises(ValueError, check_cast_bin8,
                      np.array([0, 0.1, 1], dtype=in_dtype))
        assert_raises(ValueError, check_cast_bin8,
                      np.array([0, -1, 1], dtype=in_dtype))
