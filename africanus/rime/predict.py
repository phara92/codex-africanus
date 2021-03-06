# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from collections import namedtuple
from functools import wraps

import numba
from numba import types, generated_jit, njit
import numpy as np

from ..util.docs import DocstringTemplate, on_rtd
from ..util.numba import is_numba_type_none


JONES_NOT_PRESENT = 0
JONES_1_OR_2 = 1
JONES_2X2 = 2


def _get_jones_types(name, numba_ndarray_type, corr_1_dims, corr_2_dims):
    """
    Determine which of the following three cases are valid:

    1. The array is not present (None) and therefore no Jones Matrices
    2. single (1,) or (2,) dual correlation
    3. (2, 2) full correlation

    Parameters
    ----------
    name: str
        Array name
    numba_ndarray_type: numba.type
        Array numba type
    corr_1_dims: int
        Number of `numba_ndarray_type` dimensions,
        including correlations (first option)
    corr_2_dims: int
        Number of `numba_ndarray_type` dimensions,
        including correlations (second option)

    Returns
    -------
    int
        Enumeration describing the Jones Matrix Type

        - 0 -- Not Present
        - 1 -- (1,) or (2,)
        - 2 -- (2, 2)
    """

    if is_numba_type_none(numba_ndarray_type):
        return JONES_NOT_PRESENT
    if numba_ndarray_type.ndim == corr_1_dims:
        return JONES_1_OR_2
    elif numba_ndarray_type.ndim == corr_2_dims:
        return JONES_2X2
    else:
        raise ValueError("%s.ndim not in (%d, %d)" %
                         (name, corr_1_dims, corr_2_dims))


def jones_mul_factory(have_ants, have_bl, jones_type, accumulate):
    """
    Outputs a function that multiplies some combination of
    (dde1_jones, baseline_jones, dde2_jones) together.

    Parameters
    ----------
    have_ants : boolean
        If True, indicates that antenna jones terms are present
    have_bl : boolean
        If True, indicates that baseline jones terms are present
    jones_type : int
        Type of Jones matrix
    accumulate : boolean
        If True, the result of the multiplication is accumulated
        into the output, otherwise, it is assigned

    Notes
    -----
    ``accumulate`` is treated by LLVM as a compile-time constant,
    according to https://numba.pydata.org/numba-doc/latest/glossary.html.

    Therefore in principle, the conditional checks
    involving ``accumulate`` inside the functions should
    be elided by the compiler.


    Returns
    -------
    callable
        jitted numba function performing the Jones Multiply
    """
    ex = ValueError("Invalid Jones Type %s" % jones_type)

    if have_bl and have_ants:
        if jones_type == JONES_1_OR_2:
            def jones_mul(a1j, blj, a2j, out):
                for c in range(out.shape[0]):
                    if accumulate:
                        out[c] += a1j[c] * blj[c] * np.conj(a2j[c])
                    else:
                        out[c] = a1j[c] * blj[c] * np.conj(a2j[c])

        elif jones_type == JONES_2X2:
            def jones_mul(a1j, blj, a2j, out):
                a2_xx_H = np.conj(a2j[0, 0])
                a2_xy_H = np.conj(a2j[0, 1])
                a2_yx_H = np.conj(a2j[1, 0])
                a2_yy_H = np.conj(a2j[1, 1])

                xx = blj[0, 0] * a2_xx_H + blj[0, 1] * a2_yx_H
                xy = blj[0, 0] * a2_xy_H + blj[0, 1] * a2_yy_H
                yx = blj[1, 0] * a2_xx_H + blj[1, 1] * a2_yx_H
                yy = blj[1, 0] * a2_xy_H + blj[1, 1] * a2_yy_H

                if accumulate:
                    out[0, 0] += a1j[0, 0] * xx + a1j[0, 1] * yx
                    out[0, 1] += a1j[0, 0] * xy + a1j[0, 1] * yy
                    out[1, 0] += a1j[1, 0] * xx + a1j[1, 1] * yx
                    out[1, 1] += a1j[1, 0] * xy + a1j[1, 1] * yy
                else:
                    out[0, 0] = a1j[0, 0] * xx + a1j[0, 1] * yx
                    out[0, 1] = a1j[0, 0] * xy + a1j[0, 1] * yy
                    out[1, 0] = a1j[1, 0] * xx + a1j[1, 1] * yx
                    out[1, 1] = a1j[1, 0] * xy + a1j[1, 1] * yy

        else:
            raise ex
    elif have_ants and not have_bl:
        if jones_type == JONES_1_OR_2:
            def jones_mul(a1j, a2j, out):
                for c in range(out.shape[0]):
                    if accumulate:
                        out[c] += a1j[c] * np.conj(a2j[c])
                    else:
                        out[c] = a1j[c] * np.conj(a2j[c])

        elif jones_type == JONES_2X2:
            def jones_mul(a1j, a2j, out):
                a2_xx_H = np.conj(a2j[0, 0])
                a2_xy_H = np.conj(a2j[0, 1])
                a2_yx_H = np.conj(a2j[1, 0])
                a2_yy_H = np.conj(a2j[1, 1])

                if accumulate:
                    out[0, 0] += a1j[0, 0] * a2_xx_H + a1j[0, 1] * a2_yx_H
                    out[0, 1] += a1j[0, 0] * a2_xy_H + a1j[0, 1] * a2_yy_H
                    out[1, 0] += a1j[1, 0] * a2_xx_H + a1j[1, 1] * a2_yx_H
                    out[1, 1] += a1j[1, 0] * a2_xy_H + a1j[1, 1] * a2_yy_H
                else:
                    out[0, 0] += a1j[0, 0] * a2_xx_H + a1j[0, 1] * a2_yx_H
                    out[0, 1] += a1j[0, 0] * a2_xy_H + a1j[0, 1] * a2_yy_H
                    out[1, 0] += a1j[1, 0] * a2_xx_H + a1j[1, 1] * a2_yx_H
                    out[1, 1] += a1j[1, 0] * a2_xy_H + a1j[1, 1] * a2_yy_H
        else:
            raise ex
    elif not have_ants and have_bl:
        if jones_type == JONES_1_OR_2:
            def jones_mul(blj, out):
                for c in range(out.shape[0]):
                    if accumulate:
                        out[c] += blj[c]
                    elif id(blj) == id(out):
                        pass
                    else:
                        out[c] = blj[c]

        elif jones_type == JONES_2X2:
            def jones_mul(blj, out):
                if accumulate:
                    out[0, 0] += blj[0, 0]
                    out[0, 1] += blj[0, 1]
                    out[1, 0] += blj[1, 0]
                    out[1, 1] += blj[1, 1]
                elif id(blj) == id(out):
                    pass
                else:
                    out[0, 0] = blj[0, 0]
                    out[0, 1] = blj[0, 1]
                    out[1, 0] = blj[1, 0]
                    out[1, 1] = blj[1, 1]
        else:
            raise ex
    else:
        # noop
        def jones_mul():
            pass

    return njit(nogil=True)(jones_mul)


def sum_coherencies_factory(have_ants, have_bl, jones_type):
    """ Factory function generating a function that sums coherencies """
    jones_mul = jones_mul_factory(have_ants, have_bl, jones_type, True)

    if have_ants and have_bl:
        def sum_coh_fn(time, ant1, ant2, a1j, blj, a2j, tmin, out):
            for s in range(a1j.shape[0]):
                for r, (ti, a1, a2) in enumerate(zip(time, ant1, ant2)):
                    ti -= tmin
                    for f in range(a1j.shape[3]):
                        jones_mul(a1j[s, ti, a1, f],
                                  blj[s, r, f],
                                  a2j[s, ti, a2, f],
                                  out[r, f])

    elif have_ants and not have_bl:
        def sum_coh_fn(time, ant1, ant2, a1j, blj, a2j, tmin, out):
            for s in range(a1j.shape[0]):
                for r, (ti, a1, a2) in enumerate(zip(time, ant1, ant2)):
                    ti -= tmin
                    for f in range(a1j.shape[3]):
                        jones_mul(a1j[s, ti, a1, f],
                                  a2j[s, ti, a2, f],
                                  out[r, f])

    elif not have_ants and have_bl:
        def sum_coh_fn(time, ant1, ant2, a1j, blj, a2j, tmin, out):
            for s in range(blj.shape[0]):
                for r in range(blj.shape[1]):
                    for f in range(blj.shape[2]):
                        out[r, f] += blj[s, r, f]
    else:
        # noop
        def sum_coh_fn(time, ant1, ant2, a1j, blj, a2j, tmin, out):
            pass

    return njit(nogil=True)(sum_coh_fn)


def output_factory(have_ants, have_bl, have_dies, out_dtype):
    """ Factory function generating a function that creates function output """
    if have_ants:
        def output(time_index, dde1_jones, source_coh, dde2_jones,
                   die1_jones, die2_jones):
            row = time_index.shape[0]
            chan = dde1_jones.shape[3]
            corrs = dde1_jones.shape[4:]
            return np.zeros((row, chan) + corrs, dtype=out_dtype)
    elif have_bl:
        def output(time_index, dde1_jones, source_coh, dde2_jones,
                   die1_jones, die2_jones):
            row = time_index.shape[0]
            chan = source_coh.shape[2]
            corrs = source_coh.shape[3:]
            return np.zeros((row, chan) + corrs, dtype=out_dtype)
    elif have_dies:
        def output(time_index, dde1_jones, source_coh, dde2_jones,
                   die1_jones, die2_jones):
            row = time_index.shape[0]
            chan = die1_jones.shape[2]
            corrs = die1_jones.shape[3:]
            return np.zeros((row, chan) + corrs, dtype=out_dtype)
    else:
        raise ValueError("Insufficient inputs were supplied "
                         "for determining the output shape")

    return njit(nogil=True)(output)


def add_coh_factory(have_coh):
    if have_coh:
        def add_coh(base_vis, out):
            out += base_vis
    else:
        # noop
        def add_coh(base_vis, out):
            pass

    return njit(nogil=True)(add_coh)


def apply_dies_factory(have_dies, have_coh, jones_type):
    """
    Factory function returning a function that applies
    Direction Independent Effects
    """

    # We always "have visibilities", (the output array)
    jones_mul = jones_mul_factory(have_dies, True, jones_type, False)

    if have_dies and have_coh:
        def apply_dies(time, ant1, ant2,
                       die1_jones, die2_jones,
                       tmin, out):
            # Iterate over rows
            for r, (ti, a1, a2) in enumerate(zip(time, ant1, ant2)):
                ti -= tmin

                # Iterate over channels
                for c in range(out.shape[1]):
                    jones_mul(die1_jones[ti, a1, c], out[r, c],
                              die2_jones[ti, a2, c], out[r, c])

    elif have_dies and not have_coh:
        def apply_dies(time, ant1, ant2,
                       die1_jones, die2_jones,
                       tmin, out):
            # Iterate over rows
            for r, (ti, a1, a2) in enumerate(zip(time, ant1, ant2)):
                ti -= tmin

                # Iterate over channels
                for c in range(out.shape[1]):
                    jones_mul(die1_jones[ti, a1, c], out[r, c],
                              die2_jones[ti, a2, c],
                              out[r, c])
    else:
        # noop
        def apply_dies(time, ant1, ant2,
                       die1_jones, die2_jones,
                       tmin, out):
            pass

    return njit(nogil=True)(apply_dies)


def predict_vis(time_index, antenna1, antenna2,
                dde1_jones=None, source_coh=None, dde2_jones=None,
                die1_jones=None, base_vis=None, die2_jones=None):

    have_a1 = not is_numba_type_none(dde1_jones)
    have_bl = not is_numba_type_none(source_coh)
    have_a2 = not is_numba_type_none(dde2_jones)
    have_g1 = not is_numba_type_none(die1_jones)
    have_coh = not is_numba_type_none(base_vis)
    have_g2 = not is_numba_type_none(die2_jones)

    assert time_index.ndim == 1
    assert antenna1.ndim == 1
    assert antenna2.ndim == 1

    if have_a1 ^ have_a2:
        raise ValueError("Both dde1_jones and dde2_jones "
                         "must be present or absent")

    if have_g1 ^ have_g2:
        raise ValueError("Both die1_jones and die2_jones "
                         "must be present or absent")

    # Infer the output dtype
    dtype_arrays = (dde1_jones, source_coh, dde2_jones,
                    die1_jones, base_vis, die2_jones)

    out_dtype = np.result_type(*(np.dtype(a.dtype.name)
                                 for a in dtype_arrays
                                 if not is_numba_type_none(a)))

    have_ants = have_a1 and have_a2
    have_dies = have_g1 and have_g2

    # if not (have_ants or have_bl):
    #     raise ValueError("No Jones Terms were supplied")

    if have_a1 and dde1_jones.ndim not in (5, 6):
        raise ValueError("dde1_jones.ndim %d not in (5, 6)" % dde1_jones.ndim)

    if have_a2 and dde2_jones.ndim not in (5, 6):
        raise ValueError("dde2_jones.ndim %d not in (5, 6)" % dde2_jones.ndim)

    if have_bl and source_coh.ndim not in (4, 5):
        raise ValueError("source_coh.ndim %d not in (4, 5)" % source_coh.ndim)

    if have_g1 and die1_jones.ndim not in (4, 5):
        raise ValueError("die1_jones.ndim %d not in (4, 5)" % die1_jones.ndim)

    # if have_coh and have_coh.ndim not in (3, 4):
    #     raise ValueError("have_coh.ndim %d not in (3, 4)" % have_coh.ndim)

    if have_g2 and die2_jones.ndim not in (4, 5):
        raise ValueError("die2_jones.ndim %d not in (4, 5)" % die2_jones.ndim)

    jones_types = [
        _get_jones_types("dde1_jones", dde1_jones, 5, 6),
        _get_jones_types("source_coh", source_coh, 4, 5),
        _get_jones_types("dde2_jones", dde2_jones, 5, 6),
        _get_jones_types("die1_jones", die1_jones, 4, 5),
        _get_jones_types("die2_jones", die2_jones, 4, 5)]

    ptypes = [t for t in jones_types if t != JONES_NOT_PRESENT]

    if not all(ptypes[0] == p for p in ptypes[1:]):
        raise ValueError("Jones Matrix Correlations were mismatched")

    try:
        jones_type = ptypes[0]
    except IndexError:
        raise ValueError("No Jones Matrices were supplied")

    # Create functions that we will use inside our predict function
    out_fn = output_factory(have_ants, have_bl, have_dies, out_dtype)
    sum_coh_fn = sum_coherencies_factory(have_ants, have_bl, jones_type)
    apply_dies_fn = apply_dies_factory(have_dies, have_coh, jones_type)
    add_coh_fn = add_coh_factory(have_coh)

    @wraps(predict_vis)
    def _predict_vis_fn(time_index, antenna1, antenna2,
                        dde1_jones=None, source_coh=None, dde2_jones=None,
                        die1_jones=None, base_vis=None, die2_jones=None):

        # Get the output shape
        out = out_fn(time_index, dde1_jones, source_coh, dde2_jones,
                     die1_jones, die2_jones)

        # Minimum time index, used to normalise within function
        tmin = time_index.min()

        # Sum coherencies if any
        sum_coh_fn(time_index, antenna1, antenna2,
                   dde1_jones, source_coh, dde2_jones,
                   tmin, out)

        # Add base visibilities to the output, if any
        add_coh_fn(base_vis, out)

        # Apply direction independent effects, if any
        apply_dies_fn(time_index, antenna1, antenna2,
                      die1_jones, die2_jones,
                      tmin, out)

        return out

    return _predict_vis_fn


# inspect.getargspec doesn't work on a numba dispatcher object
# so rtd fails.
if not on_rtd():
    predict_vis = generated_jit(nopython=True, nogil=True, cache=True)(
                                predict_vis)


PREDICT_DOCS = DocstringTemplate(r"""
Multiply Jones terms together to form model visibilities according
to the following formula:

.. math::


    V_{pq} = G_{p} \left(
        B_{pq} + \sum_{s} A_{ps} X_{pqs} A_{qs}^H
        \right) G_{q}^H

where for antenna :math:`p` and :math:`q`, and source :math:`s`:


- :math:`B_{{pq}}` represent base coherencies.
- :math:`E_{{ps}}` represents Direction-Dependent Jones terms.
- :math:`X_{{pqs}}` represents a coherency matrix (per-source).
- :math:`G_{{p}}` represents Direction-Independent Jones terms.

Generally, :math:`E_{ps}`, :math:`G_{p}`, :math:`X_{pqs}`
should be formed by using the `RIME API <rime-api-anchor_>`_ functions
and combining them together with :func:`~numpy.einsum`.

**Please read the Notes**

Notes
-----
* Direction-Dependent terms (dde{1,2}_jones) and
  Independent (die{1,2}_jones) are optional,
  but if one is present, the other must be present.
* The inputs to this function involve ``row``, ``time``
  and ``ant`` (antenna) dimensions.
* Each ``row`` is associated with a pair of antenna Jones matrices
  at a particular timestep via the
  ``time_index``, ``antenna1`` and ``antenna2`` inputs.
* The ``row`` dimension must be an increasing partial order in time.
$(extra_notes)


Parameters
----------
time_index : $(array_type)
    Time index used to look up the antenna Jones index
    for a particular baseline.
    shape :code:`(row,)`.
antenna1 : $(array_type)
    Antenna 1 index used to look up the antenna Jones
    for a particular baseline.
    with shape :code:`(row,)`.
antenna2 : $(array_type)
    Antenna 2 index used to look up the antenna Jones
    for a particular baseline.
    with shape :code:`(row,)`.
dde1_jones : $(array_type), optional
    :math:`A_{ps}` Direction-Dependent Jones terms for the first antenna.
    shape :code:`(source,time,ant,chan,corr_1,corr_2)`
source_coh : $(array_type), optional
    :math:`X_{pqs}` Direction-Dependent Coherency matrix for the baseline.
    with shape :code:`(source,row,chan,corr_1,corr_2)`
dde2_jones : $(array_type), optional
    :math:`A_{qs}` Direction-Dependent Jones terms for the second antenna.
    shape :code:`(source,time,ant,chan,corr_1,corr_2)`
die1_jones : $(array_type), optional
    :math:`G_{ps}` Direction-Independent Jones terms for the
    first antenna of the baseline.
    with shape :code:`(time,ant,chan,corr_1,corr_2)`
base_vis : $(array_type), optional
    :math:`B_{pq}` base visibilities, added to source coherency summation
    *before* multiplication with `die1_jones` and `die2_jones`.
die2_jones : $(array_type), optional
    :math:`G_{ps}` Direction-Independent Jones terms for the
    second antenna of the baseline.
    with shape :code:`(time,ant,chan,corr_1,corr_2)`

Returns
-------
$(array_type)
    Model visibilities of shape :code:`(row,chan,corr_1,corr_2)`
""")


try:
    predict_vis.__doc__ = PREDICT_DOCS.substitute(
                            array_type=":class:`numpy.ndarray`",
                            extra_notes="")
except AttributeError:
    pass
