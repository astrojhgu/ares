"""

test_cxrb_helium.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Fri May 24 13:07:09 2013

Description: Include helium opacity.

"""

import ares
import numpy as np
import matplotlib.pyplot as pl

# Redshift regime
zi, zf = (10, 40)

# Initialize radiation background
pars = \
{
 'sfrd': lambda z: 1e-2 / (1. + z)**3.,
 'source_type': 'bh',
 'spectrum_type': 'pl',
 'spectrum_alpha': -1.5,
 'spectrum_Emin': 2e2,
 'spectrum_Emax': 3e4,
 'spectrum_EminNorm': 2e2,
 'spectrum_EmaxNorm': 3e4,
 'approx_xray': False,
 'initial_redshift': zi,
 'final_redshift': zf,
 'redshift_bins': 400,
}

pars2 = pars.copy(); pars2.update({'approx_helium': 1, 'Z':[1,2]})

rad_h = ares.solvers.UniformBackground(**pars)
rad_he = ares.solvers.UniformBackground(**pars2)

E = np.logspace(2, 4)

flux_h = map(lambda E: rad_h.AngleAveragedFlux(10, E, xavg=lambda z: 0.0), E)
flux_he = map(lambda E: rad_he.AngleAveragedFlux(10, E, xavg=lambda z: 0.0), E)

pl.loglog(E, flux_h, color='k', label='H-only')
pl.loglog(E, flux_he, color='b', label='H+He')
pl.xlabel(ares.util.labels['E'])
pl.ylabel(ares.util.labels['flux'])
pl.legend(loc='best', frameon=False)
pl.title('X-ray Background at z = %g' % zi)
pl.ylim(1e-30, 1e-18)