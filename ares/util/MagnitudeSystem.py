"""

MagnitudeSystem.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Sat Sep  5 15:51:39 PDT 2015

Description: Utilities for converting magnitudes to luminosities and such.

"""

import numpy as np
from ..physics.Cosmology import Cosmology
from ..physics.Constants import cm_per_pc

norm_AB = 3631. * 1e-23  # 3631 Jansky in cgs, i.e., 
                         # 3631 * 1e-23 erg / s / cm**2 / Hz

class MagnitudeSystem(Cosmology):
    #def __init__(self, **kwargs):
    #    
    #    if not kwargs:
    #        kw = cosm
    #    else:
    #        kw = {key : kwargs[key] for key in cosm}
    #    
    #    Cosmology.__init__(self, **kw)
    
    def mab_to_L(self, mag, z=None, dL=None):
        """
        Convert AB magnitude [APPARENT] to rest-frame luminosity.
        """
        pass
    
    def MAB_to_L(self, mag, z=None, dL=None):
        """
        Convert AB magnitude [ABSOLUTE] to rest-frame luminosity.
        
        Parameters
        ----------
        mag : int, float
            Absolute magnitude in AB system.
        z : int, float
            Redshift of object
        dL : int, float
            Luminosity distance of object [cm]

        Currently this is dumb: doesn't need to depend on luminosity.

        Returns
        -------
        Luminosity in erg / s / Hz.
            
        """
        
        assert (z is not None) or (dL is not None)
        
        if z is not None:
            dL = self.LuminosityDistance(z)
        
        # Apparent magnitude
        m = mag + 5. * (np.log10(dL/ cm_per_pc) - 1.) 

        # Luminosity!    
        return 10**(m / -2.5) * norm_AB * 4. * np.pi * dL**2

    def L_to_MAB(self, L, z=None, dL=None):
        # absolute magnitude
        assert (z is not None) or (dL is not None)
        
        if z is not None:
            dL = self.LuminosityDistance(z)
         
        #    
        m = -2.5 * np.log10(L  / (norm_AB * 4. * np.pi * dL**2))
        
        return m - 5. * (np.log10(dL / cm_per_pc) - 1.) 

    def mAB_to_flux_density(self, mag):
        pass
    
