# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np

from ..util.requirements import requires_optional

try:
    import pyrap.measures
    import pyrap.quanta as pq
except ImportError:
    have_casa_parangles = False
else:
    have_casa_parangles = True

    # Create a measures server
    meas_serv = pyrap.measures.measures()


@requires_optional('pyrap.measures', 'pyrap.quanta')
def casa_parallactic_angles(times, antenna_positions, field_centre,
                            zenith_frame='AZEL'):
    """
    Computes parallactic angles per timestep for the given
    reference antenna position and field centre.
    """

    # Create direction measure for the zenith
    zenith = meas_serv.direction(zenith_frame, '0deg', '90deg')

    # Create position measures for each antenna
    reference_positions = [meas_serv.position(
                                'itrf',
                                *(pq.quantity(x, 'm') for x in pos))
                           for pos in antenna_positions]

    # Compute field centre in radians
    fc_rad = meas_serv.direction('J2000', *(pq.quantity(f, 'rad')
                                            for f in field_centre))

    return np.asarray([
        # Set current time as the reference frame
        meas_serv.do_frame(meas_serv.epoch("UTC", pq.quantity(t, "s")))
        and
        [   # Set antenna position as the reference frame
            meas_serv.do_frame(rp)
            and
            meas_serv.posangle(fc_rad, zenith).get_value("rad")
            for rp in reference_positions
        ]
        for t in times])
