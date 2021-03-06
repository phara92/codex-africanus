#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `codex-africanus` package."""

import numba
import numpy as np

import pytest


def rf(*a, **kw):
    return np.random.random(*a, **kw)


def rc(*a, **kw):
    return rf(*a, **kw) + 1j*rf(*a, **kw)


@pytest.mark.parametrize('corr_shape, idm, einsum_sig1, einsum_sig2', [
    ((1,), (1,), "srci,srci,srci->rci", "rci,rci,rci->rci"),
    ((2,), (1, 1), "srci,srci,srci->rci", "rci,rci,rci->rci"),
    ((2, 2), ((1, 0), (0, 1)),
     "srcij,srcjk,srckl->rcil", "rcij,rcjk,rckl->rcil"),
])
@pytest.mark.parametrize('a1j,blj,a2j', [
    [True, True, True],
    [True, False, True],
    [False, True, False],
])
@pytest.mark.parametrize('g1j,bvis,g2j', [
    [True, True, True],
    [True, False, True],
    [False, True, False],
])
def test_predict_vis(corr_shape, idm, einsum_sig1, einsum_sig2,
                     a1j, blj, a2j, g1j, bvis, g2j):
    from africanus.rime.predict import predict_vis

    s = 2       # sources
    t = 4       # times
    a = 4       # antennas
    c = 5       # channels
    r = 10      # rows

    a1_jones = rc((s, t, a, c) + corr_shape)
    bl_jones = rc((s, r, c) + corr_shape)
    a2_jones = rc((s, t, a, c) + corr_shape)
    g1_jones = rc((t, a, c) + corr_shape)
    base_vis = rc((r, c) + corr_shape)
    g2_jones = rc((t, a, c) + corr_shape)

    #  Row indices into the above time/ant indexed arrays
    time_idx = np.asarray([0, 0, 1, 1, 2, 2, 2, 2, 3, 3])
    ant1 = np.asarray([0, 0, 0, 0, 1, 1, 1, 2, 2, 3])
    ant2 = np.asarray([0, 1, 2, 3, 1, 2, 3, 2, 3, 3])

    assert ant1.size == r

    model_vis = predict_vis(time_idx, ant1, ant2,
                            a1_jones if a1j else None,
                            bl_jones if blj else None,
                            a2_jones if a2j else None,
                            g1_jones if g1j else None,
                            base_vis if bvis else None,
                            g2_jones if g2j else None)

    assert model_vis.shape == (r, c) + corr_shape

    def _id(array):
        return np.broadcast_to(idm, array.shape)

    # For einsum, convert (time, ant) dimensions to row
    # or ID matrices if the input is present
    a1_jones = a1_jones[:, time_idx, ant1] if a1j else _id(bl_jones)
    bl_jones = bl_jones if blj else _id(bl_jones)
    a2_jones = a2_jones[:, time_idx, ant2].conj() if a2j else _id(bl_jones)

    v = np.einsum(einsum_sig1, a1_jones, bl_jones, a2_jones)

    if bvis:
        v += base_vis

    # Convert (time, ant) dimensions to row or
    # or ID matrices if input is not present
    g1_jones = g1_jones[time_idx, ant1] if g1j else _id(v)
    g2_jones = g2_jones[time_idx, ant2].conj() if g2j else _id(v)

    v = np.einsum(einsum_sig2, g1_jones, v, g2_jones)

    assert np.allclose(v, model_vis)


@pytest.mark.parametrize('corr_shape, idm, einsum_sig1, einsum_sig2', [
    ((1,), (1,), "srci,srci,srci->rci", "rci,rci,rci->rci"),
    ((2,), (1, 1), "srci,srci,srci->rci", "rci,rci,rci->rci"),
    ((2, 2), ((1, 0), (0, 1)),
     "srcij,srcjk,srckl->rcil", "rcij,rcjk,rckl->rcil"),
])
@pytest.mark.parametrize('a1j,blj,a2j', [
    [True, True, True],
    [True, False, True],
    [False, True, False],
])
@pytest.mark.parametrize('g1j,bvis,g2j', [
    [True, True, True],
    [True, False, True],
    [False, True, False],
])
def test_dask_predict_vis(corr_shape, idm, einsum_sig1, einsum_sig2,
                          a1j, blj, a2j, g1j, bvis, g2j):

    da = pytest.importorskip('dask.array')
    import numpy as np
    from africanus.rime.predict import predict_vis as np_predict_vis
    from africanus.rime.dask import predict_vis

    # chunk sizes
    sc = (2, 3, 4)    # sources
    tc = (2, 1, 1)    # times
    rrc = (4, 4, 2)   # rows
    ac = (4,)         # antennas
    cc = (3, 2)       # channels

    # dimension sizes
    s = sum(sc)       # sources
    t = sum(tc)       # times
    a = sum(ac)       # antennas
    c = sum(cc)       # channels
    r = sum(rrc)      # rows

    a1_jones = rc((s, t, a, c) + corr_shape)
    a2_jones = rc((s, t, a, c) + corr_shape)
    bl_jones = rc((s, r, c) + corr_shape)
    g1_jones = rc((t, a, c) + corr_shape)
    base_vis = rc((r, c) + corr_shape)
    g2_jones = rc((t, a, c) + corr_shape)

    #  Row indices into the above time/ant indexed arrays
    time_idx = np.asarray([0, 0, 1, 1, 2, 2, 2, 2, 3, 3])
    ant1 = np.asarray([0, 0, 0, 0, 1, 1, 1, 2, 2, 3])
    ant2 = np.asarray([0, 1, 2, 3, 1, 2, 3, 2, 3, 3])

    assert ant1.size == r

    np_model_vis = np_predict_vis(time_idx, ant1, ant2,
                                  a1_jones if a1j else None,
                                  bl_jones if blj else None,
                                  a2_jones if a2j else None,
                                  g1_jones if g1j else None,
                                  base_vis if bvis else None,
                                  g2_jones if g2j else None)

    da_time_idx = da.from_array(time_idx, chunks=rrc)
    da_ant1 = da.from_array(ant1, chunks=rrc)
    da_ant2 = da.from_array(ant2, chunks=rrc)

    da_a1_jones = da.from_array(a1_jones, chunks=(sc, tc, ac, cc) + corr_shape)
    da_bl_jones = da.from_array(bl_jones, chunks=(sc, rrc, cc) + corr_shape)
    da_a2_jones = da.from_array(a2_jones, chunks=(sc, tc, ac, cc) + corr_shape)
    da_g1_jones = da.from_array(g1_jones, chunks=(tc, ac, cc) + corr_shape)
    da_base_vis = da.from_array(base_vis, chunks=(rrc, cc) + corr_shape)
    da_g2_jones = da.from_array(g2_jones, chunks=(tc, ac, cc) + corr_shape)

    model_vis = predict_vis(da_time_idx, da_ant1, da_ant2,
                            da_a1_jones if a1j else None,
                            da_bl_jones if blj else None,
                            da_a2_jones if a2j else None,
                            da_g1_jones if g1j else None,
                            da_base_vis if bvis else None,
                            da_g2_jones if g2j else None)

    model_vis = model_vis.compute()

    if not np.allclose(model_vis, np_model_vis):
        diff = model_vis - np_model_vis
        diff[np.abs(diff) < 1e-10] = 0.0
        problems = np.array(np.nonzero(diff)).T

        for p in (tuple(p.tolist()) for p in problems):
            print(p, model_vis[p], np_model_vis[p])

    assert np.allclose(model_vis, np_model_vis)
