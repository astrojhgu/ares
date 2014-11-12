"""

test_fitting_fcoll.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Mon May 12 14:19:33 MDT 2014

Description: Can run this in parallel.

"""

import time
import numpy as np
import matplotlib.pyplot as pl
from ares.inference import ModelFit

blobs = (['igm_Tk', 'igm_heat', 'cgm_Gamma', 'cgm_h_2', 'Ts', 'Ja', 'dTb'], 
        ['B', 'C', 'D'])

# These go to every calculation
base_pars = \
{
 'final_redshift': 8.,
 'inline_analysis': blobs,
 'stop': 'D',
}

# Initialize fitter
fit = ModelFit(**base_pars)

# Input model: all defaults
sim = ares.simulations.Global21cm()
fit.mu = ares.analysis.Global21cm(sim).turning_points

# Set axes of parameter space
fit.set_axes(['fX', 'Tmin'], is_log=[True]*2)
fit.priors = {'fX': ['uniform', -3., 3.], 'Tmin': ['uniform', 2.5, 5.]}

# Set errors
fit.set_error(error1d=[0.5, 0.5, 0.5, 5., 5., 5.])

# Defines order of errors
fit.measurement_map = \
    [('B', 0), ('C', 0), ('D', 0),
     ('B', 1), ('C', 1), ('D', 1)]

fit.nwalkers = 8

# Run it!
t1 = time.time()
fit.run(prefix='test_fcoll', steps=50, clobber=True, save_freq=1)
t2 = time.time()

print "Run complete in %.4g minutes.\n" % ((t2 - t1) / 60.)

