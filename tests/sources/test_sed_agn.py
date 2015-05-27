"""

test_sed_mcd.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Thu May  2 10:46:44 2013

Description: Plot a simple power-law spectrum.

"""

import ares
import numpy as np
import matplotlib.pyplot as pl

pars = \
{
 'source_type': 'bh', 
 'spectrum_type': 'qso',
 'spectrum_Emin': 1,
 'spectrum_Emax': 3e4,
}

src = ares.sources.RadiationSource(init_tabs=False, **pars)
bh = ares.analysis.Source(src)

ax = bh.PlotSpectrum()

ax.set_ylim(1e-8, 1)
pl.draw()


