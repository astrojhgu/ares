"""

Halo.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Thu May 28 16:22:44 MDT 2015

Description: 

"""

import numpy as np
from .Population import Population
from scipy.integrate import cumtrapz
from ..physics import HaloMassFunction
from ..util.PrintInfo import print_pop
from ..util.Math import central_difference
from ..physics.Constants import cm_per_mpc, s_per_yr, g_per_msun

class HaloPopulation(Population):
    def __init__(self, **kwargs):
        
        # This is basically just initializing an instance of the cosmology
        # class. Also creates the parameter file attribute ``pf``.
        Population.__init__(self, **kwargs)

    @property
    def parameterized(self):
        if not hasattr(self, '_parameterized'):
            not_parameterized = (self.pf['pop_k_ion_igm']) is None
            not_parameterized &= (self.pf['pop_k_ion_cgm']) is None
            not_parameterized &= (self.pf['pop_k_heat_igm']) is None
            self._parameterized = not not_parameterized

        return self._parameterized

    @property
    def info(self):
        if not self.parameterized:
            try:
                print_pop(self)
            except AttributeError:
                pass

    @property
    def dndm(self):
        if not hasattr(self, '_fcoll'):
            self._init_fcoll()
    
        return self._dndm

    @property
    def fcoll(self):
        if not hasattr(self, '_fcoll'):
            self._init_fcoll()
    
        return self._fcoll

    @property
    def dfcolldz(self):
        if not hasattr(self, '_dfcolldz'):
            self._init_fcoll()

        return self._dfcolldz

    def dfcolldt(self, z):
        return self.dfcolldz(z) / self.cosm.dtdz(z)    

    def _set_fcoll(self, Tmin, mu):
        self._fcoll, self._dfcolldz, self._d2fcolldz2 = \
            self.halos.build_1d_splines(Tmin, mu)

    @property
    def halos(self):
        if not hasattr(self, '_halos'):
            if self.pf['hmf_instance'] is not None:
                self._halos = self.pf['hmf_instance']
            else:
                self._halos = HaloMassFunction(**self.pf)
                
        return self._halos

    def update_Mmin(self, z, Mmin):
        """
        Given the redshift and minimum mass, create a new _dfcolldz function.
        """
        
        if not hasattr(self, '_counter'):
            self._counter = 0
            
        # Data containers    
        if not hasattr(self, '_z_list'):
            self._z_list = []
            self._fcoll_list = []
        
        # Brute-force
        if self._counter < 5:
            Tmin = self.halos.VirialTemperature(Mmin, z, mu=0.6)
            self._set_fcoll(Tmin, mu=0.6)
            
            self._z_list.append(z)
            self._fcoll_list.append(self.fcoll(z))
                            
        else:
                        
            # Do something cool!
            
            # Step 1: Calculate fcoll(z, Mmin)
            
            fcoll = self.halos.fcoll_2d(z, np.log10(Mmin))
            

            
            # Step 2: Append to lists
            
            self._z_list.append(z)
            self._fcoll_list.append(fcoll)
            
            # Step 2.5: Take derivative!
            
            
            _ztab, _dfcolldz_tab = \
                central_difference(self._z_list, self._fcoll_list)
            
            
            # Step 3: Create extrapolants
            z_hi, z_mid, z_lo = _ztab[-3:]
            dfcdz_hi, dfcdz_mid, dfcdz_lo = _dfcolldz_tab[-3:]
            
            dfcdz_p = (dfcdz_lo - dfcdz_hi) / (z_lo - z_hi)
            dfcdz_a = (dfcdz_mid - dfcdz_hi) / (z_mid - z_hi)
            dfcdz_b = (dfcdz_lo - dfcdz_mid) / (z_lo - z_mid)
            #print dfcdz_hi, dfcdz_mid, dfcdz_lo
            #self._dfcolldz = lambda z: abs(dfcdz_hi + dfcdz_a*(z-z_hi) + ((dfcdz_b-dfcdz_a)/(z_lo-z_hi))*(z-z_mid)*(z-z_hi)) 

            self._dfcolldz = lambda z: abs(dfcdz_p * (z - z_lo) + dfcdz_lo)
            
                
        #if self._counter > 8:
        #    raise ValueError('hey')
        #
        self._counter += 1
        
    def _init_fcoll(self):
        # Halo stuff
        if self.pf['pop_sfrd'] is not None:
            return

        #if self.pf['pop_feedback']:
        #    # 2-D function in this case, of (redshift, logMmin)
        #    self._fcoll = self.halos.fcoll
        #    self._dfcolldz = self.halos.dfcolldz
        if self.pf['pop_fcoll'] is None:
            self._set_fcoll(self.pf['pop_Tmin'], self.pf['mu'])
        else:
            self._fcoll, self._dfcolldz = \
                self.pf['pop_fcoll'], self.pf['pop_dfcolldz']
    
    def iMAR(self, z, source=None):
        """
        The integrated DM accretion rate.
    
        Parameters
        ----------
        z : int, float
            Redshift
        source : str
            Can be a litdata module, e.g., 'mcbride2009'.
    
        Returns
        -------
        Integrated DM mass accretion rate in units of Msun/yr/cMpc**3.
    
        """    
    
        return self.cosm.rho_m_z0 * self.dfcolldt(z) * cm_per_mpc**3 \
                * s_per_yr / g_per_msun
    
    #@property
    #def _MAR_tab(self):
    #    if not hasattr(self, '_MAR_tab_'):
    #        self._MAR_tab_ = {}
    #    return self._MAR_tab_
    

        
        
        