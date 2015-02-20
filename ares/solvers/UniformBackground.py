"""

UniformBackground.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Wed Sep 24 15:15:36 MDT 2014

Description: 

"""

import numpy as np
from math import ceil
import os, re, types, gc
from ..util.Misc import logbx
from ..util import ParameterFile
from ..physics.Constants import *
from ..static import GlobalVolume
from ..util.PrintInfo import print_rb
from scipy.interpolate import interp1d
from ..physics import Hydrogen, Cosmology
from ..populations import CompositePopulation
from scipy.integrate import quad, romberg, romb, trapz, simps
from ..populations import BlackHolePopulation, StellarPopulation

try:
    import h5py
except ImportError:
    pass
     
try:
    from mpi4py import MPI
    rank = MPI.COMM_WORLD.rank
    size = MPI.COMM_WORLD.size
except ImportError:
    rank = 0
    size = 1
    
ARES = os.getenv('ARES')
            
log10 = np.log(10.)    # for when we integrate in log-space
four_pi = 4. * np.pi

E_th = np.array([13.6, 24.4, 54.4])

# Put this stuff in utils
defkwargs = \
{
 'zf':None, 
 'xray_flux':None,  
 'xray_emissivity': None, 
 'lw_flux':None,
 'lw_emissivity': None,
 'tau':None, 
 'return_rc': False, 
 'energy_units':False, 
 'xavg': 0.0,
 'zxavg':0.0,   
}       

class UniformBackground:
    def __init__(self, grid=None, use_tab=True, **kwargs):
        """
        Initialize a UniformBackground object.
        
        Creates an object capable of evolving the radiation background created
        by some population of objects, which are characterized by a comoving 
        volume emissivity and a spectrum. The evolution of the IGM opacity can 
        be computed self-consistently or imposed artificially.
        
        Parameters
        ----------
        grid : instance
            ares.static.Grid instance
            
        """
                
        self.pf = ParameterFile(**kwargs)

        # Some useful physics modules
        if grid is not None:
            self.cosm = grid.cosm
        else:
            self.cosm = Cosmology()

        self.hydr = Hydrogen(self.cosm, 
            approx_Salpha=self.pf['approx_Salpha'], nmax=self.pf['lya_nmax'])

        self._set_sources()
        self._set_integrator()

        # IGM instance
        self.volume = GlobalVolume(self, use_tab=use_tab)

        #if self.pf['verbose'] and \
        #    (not self.pf['approx_lwb'] or not self.pf['approx_xrb']):
        #     print_rb(self)

    def _set_sources(self):
        """
        Initialize population(s) of radiation sources!
        """

        self.sources = CompositePopulation(**self.pf).pops
        self.Ns = len(self.sources)

        # Determine if backgrounds are approximate or not
        self.approx_all_xrb = 1
        self.approx_all_lwb = 1
        for pop in self.sources:
            self.approx_all_xrb *= pop.pf['approx_xrb']
            self.approx_all_lwb *= pop.pf['approx_lwb']

        if self.approx_all_xrb * self.approx_all_lwb:
            return

        # Make 
        self.all_discrete_lwb = 1
        self.all_discrete_xrb = 1
        for source in self.sources:
            self.all_discrete_lwb *= source.pf['is_lya_src']
            self.all_discrete_xrb *= source.pf['is_heat_src_igm']
        
        #if self.pf['source_type'] == 'star':
        #    self.pop = StellarPopulation(**kwargs)
        #elif self.pf['source_type'] == 'bh':
        #    self.pop = BlackHolePopulation(**kwargs)
        #else:
        #    raise ValueError('source_type %s not recognized.' \
        #        % self.pf['source_type'])

    def _set_integrator(self):    
        """
        Initialize attributes pertaining to numerical integration.
        """
    
        # For integration over redshift / frequency
        self._integrator = self.pf["unsampled_integrator"]
        self._sampled_integrator = self.pf["sampled_integrator"]
        self._rtol = self.pf["integrator_rtol"]
        self._atol = self.pf["integrator_atol"]
        self._divmax = int(self.pf["integrator_divmax"])
    
    def update_rate_coefficients(self, data, t):
        """
        Compute ionization and heating rate coefficients.
        """

        # update optical depth first

        return rcs

    def BroadBandFlux(self):
        pass

    def AngleAveragedFlux(self, z, E, popid=0, **kwargs):
        """
        Compute flux at observed redshift z and energy E (eV).

        Local flux (i.e. flux at redshift z) depends (potentially) on emission 
        from sources at all redshifts z' > z. This method performs an integral
        over redshift, properly accounting for geometrical dilution, redshift,
        source SEDs, and the fact that emissivities were (possibly) different
        at higher redshift. That is, we actually solve the cosmological 
        radiative transfer equation.

        Parameters
        ----------
        z : float
            observer redshift
        E : float
            observed photon energy (eV)

        ===============
        relevant kwargs
        ===============
        tau : func, e.g. tau = lambda E, z1, z2: 0.0
            If supplied, represents the optical depth between redshifts z1
            and z2 as a function of observed energy E.
        xavg : func, array
            Average ionized fraction. Can be function of redshift, or array
            of values.
        zxavg : array
            If xavg is an array, this is the array of corresponding redshifts.  
        zf : float
            Upper limit of redshift integration (i.e. exclude emission from
            sources at z' > zf).
    
        Notes
        -----
        If none of the "relevant kwargs" are passed, will assume a neutral 
        medium.
    
        Returns
        -------
        Flux in units of s**-1 cm**-2 Hz**-1 sr**-1.
    
        See Also
        --------
        AngleAveragedFluxSlice : the function we're integrating over.
    
        """
        
        pop = self.sources[popid]
    
        if E < E_LyA:
            thin = False
            if 'tau' in kwargs:
                if kwargs['tau'] == 0.0:
                    thin = True
    
            flux = self.LymanWernerFlux(z, E, **kwargs)  
    
            if thin:
                return flux
    
            ze = (E_LyA / E) * (1. + z) - 1.
            return flux + self.LymanAlphaFlux(ze, **kwargs) \
                * ((1. + z) / (1. + ze))**2
    
        if E <= E_LL:
            return self.LymanWernerFlux(z, E, **kwargs)
    
        kw = defkwargs.copy()
        kw.update(kwargs)
    
        # Set limits of integration in redshift space
        zi = max(z, pop.zdead)
        if kw['zf'] is None:
            zf = pop.zform
        else:
            zf = kw['zf']
    
        # Normalize to help integrator
        Jc = 1e-21
    
        # Define integrand              
        #if kw['tau'] is not None:  # like zarr
        #    if type(kw['tau']) is types.FunctionType:
        #        integrand = lambda zz: self.AngleAveragedFluxSlice(z, E, zz,
        #            **kwargs) / Jc
        #    else:
        #        # Compute flux at this energy due to emission at z' > z
        #        integrand = np.zeros(len(kw['zxavg']))
        #        for i in np.arange(len(kw['zxavg'])):
        #            integrand[i] = self.AngleAveragedFluxSlice(z, E, 
        #                kw['zxavg'][i], tau=kw['tau'][i],
        #                xray_emissivity=None) / Jc
    
        #if kw[''] is not None:
        #if type(kw['xavg']) is types.FunctionType:
        integrand = lambda zu: self.AngleAveragedFluxSlice(z, E, zu,
            xavg=kw['xavg']) / Jc
        #else:
        #    integrand = np.array(map(lambda zu: \
        #        self.AngleAveragedFluxSlice(z, E, zu,
        #        xavg=kw['xavg'], zxavg=kw['zxavg']), kw['zxavg'])) / Jc
        #else:
        #    # Assume neutral medium
        #    integrand = lambda zu: self.AngleAveragedFluxSlice(z, E, zu,
        #        h_2=lambda zz: 0.0) / Jc
    
        # Compute integral
        if type(integrand) == types.FunctionType:
            if pop.burst:
                raise ValueError('Burst needs correctness-check.')
                #flux = integrand(self.pop.zform)
            elif self._integrator == 'quad':
                flux = quad(integrand, zi, zf,
                    epsrel=self._rtol, epsabs=self._atol, limit=self._divmax)[0]
            elif self._integrator == 'romb':
                flux = romberg(integrand, zi, zf,
                    tol=self._atol, divmax=self._divmax)
            else:
                raise ValueError('Uncrecognized integrator \'%s\'' \
                    % self._integrator)
        else:
            if self._sampled_integrator == 'simps':
                flux = simps(integrand, x=kw['zxavg'], even='first')
            elif self._sampled_integrator == 'trapz':
                flux = trapz(integrand, x=kw['zxavg'])
            elif self._sampled_integrator == 'romb':
    
                assert logbx(2, len(kw['zxavg']) - 1) % 1 == 0, \
                    "If sampled_integrator == 'romb', redshift_bins must be a power of 2 plus one."
    
                flux = romb(integrand, dx=np.diff(kw['zxavg'])[0])   
            else:
                raise ValueError('Uncrecognized integrator \'%s\'' \
                    % self._sampled_integrator)
    
        # Flux in units of photons s^-1 cm^-2 Hz^-1 sr^-1                                        
        flux *= Jc
    
        # Possibly convert to energy flux units
        if kw['energy_units']:
            flux *= E * erg_per_ev
    
        return flux
    
    def AngleAveragedFluxSlice(self, z, E, zp, popid=0, **kwargs):
        """
        Compute flux at observed redshift z due to sources at higher redshift.
    
        This is the integrand of 'AngleAveragedFlux,' the integral over 
        redshift we must compute to determine the specific flux at any given 
        redshift. It is the contribution to the specific flux at observed
        redshift z from sources at a single redshift, zp > z.
    
        Parameters
        ----------
        z : float
            observer redshift
        E : float
            observed photon energy (eV)
        zp : float
            redshift where photons were emitted
    
        Notes
        -----
        Will assume optically thin medium if none of the following kwargs
        are passed: tau, xavg, emissivity.    
    
        ===============
        relevant kwargs
        ===============
        tau : func, e.g. tau = lambda z1, z2, E: 0.0 # const. tau
            If supplied, represents the optical depth between redshifts z1
            and z2 as a function of observed energy E. 
        xavg : func, np.ndarray
            Average ionized fraction. Can be function of redshift, or array
            of values
        zxavg : np.ndarray
            If xavg is an array, this is the array of corresponding redshifts.
        xray_emissivity : np.ndarray
    
        Returns
        -------
        Flux in units of s**-1 cm**-2 Hz**-1 sr**-1.
    
        See Also
        --------
        AngleAveragedFlux : integrates over this function.
    
        """
    
        pop = self.sources[popid]
    
        kw = defkwargs.copy()
        kw.update(kwargs)
    
        if kw['xray_emissivity'] is None: # should include LyA too
            H = self.cosm.HubbleParameter(zp)
            E0 = self.volume.RestFrameEnergy(z, E, zp)
            epsilonhat = pop.NumberEmissivity(zp, E0)
            epsilonhat_over_H = epsilonhat / H
    
            if (E0 > pop.rs.Emax) or (E0 < pop.rs.Emin):
                return 0.0
    
        else:
            epsilonhat_over_H = kw['xray_emissivity']
    
        # Compute optical depth (perhaps)
        if kw['tau'] is not None:
            if type(kw['tau']) is types.FunctionType:
                tau = kw['tau'](z, zp, E)
            else:
                tau = kw['tau']
        elif kw['xavg'] is not None:
            if E > E_LL:
                tau = self.volume.OpticalDepth(z, zp, E, xavg=kw['xavg'],
                    zxavg=kw['zxavg'])
            else:
                tau = 0.0
        else:
            tau = self.volume.OpticalDepth(z, zp, E, xavg=kw['xavg'])
    
        return c * (1. + z)**2 * epsilonhat_over_H * np.exp(-tau) / four_pi
    
    def LWBackground(self, popid=0):
        """
        Compute LW Background over all redshifts.
    
        Returns
        -------
        Redshifts, photon energies, and fluxes, (z, E, flux).
        The flux array has shape (# redshift points, # frequency points).
        Each of these are lists, one element per Lyman-n band.
    
        """
        
        # Now, compute background flux
        lwrb = self.LWFluxGenerator()
    
        Nn = len(self.volume.lwb_En)
        fluxes = [np.zeros_like(self.volume.lwb_emiss[i][popid]) \
            for i in range(Nn)]
        
        for i, flux in enumerate(lwrb):
            
            # Since we're going from high-z to low-z
            j = len(self.volume.lwb_zl) - i - 1
            
            for n in range(Nn):
                fluxes[n][j] = flux[n]
    
        self.flux_En = fluxes

        return self.volume.lwb_zl, self.volume.lwb_E, \
            self._flatten_flux(fluxes)

    def _flatten_flux(self, flux):
        """
        Take fluxes sorted by Lyman-n band and flatten to single energy
        dimension.
        """
        
        to_return = np.zeros([len(self.volume.lwb_zl), len(self.volume.lwb_E)])

        k = 0
        for i, n in enumerate(self.volume.lwb_n):

            for j, nrg in enumerate(self.volume.lwb_En[i]):
                to_return[:,k] = flux[i][:,j]

                k += 1

        return to_return
    
    def LymanWernerFlux(self, z, E, popid=0, **kwargs):
        """
        Compute flux at observed redshift z and energy E (eV).
    
        Same as AngleAveragedFlux, but for emission in the Lyman-Werner band.
    
        Parameters
        ----------
        z : float
            observer redshift
        E : float
            observed photon energy (eV)
    
        ===============
        relevant kwargs
        ===============
        tau : func, e.g. tau = lambda E, z1, z2: 0.0 # const. tau
            If supplied, represents the optical depth between redshifts z1
            and z2 as a function of observed energy E.
        xavg : func, array
            Average ionized fraction. Can be function of redshift, or array
            of values
        zxavg : array
            If xavg is an array, this is the array of corresponding redshifts.  
        zf : float
            Upper limit of redshift integration (i.e. exclude emission from
            sources at z' > zf).
    
        Returns
        -------
        Flux in units of s**-1 cm**-2 Hz**-1 sr**-1
    
        See Also
        --------
        AngleAveragedFluxSlice : the function we're integrating over.
    
        """
        
        pop = self.sources[popid]
    
        kw = defkwargs.copy()
        kw.update(kwargs)
    
        # Closest Lyman line (from above)
        n = ceil(np.sqrt(E_LL / (E_LL - E)))
    
        if n > self.pf['lya_nmax']:
            return 0.0
    
        En =  E_LL * (1. - 1. / n**2)
    
        # Corresponding zmax ("dark screen" as Z. Haiman likes to say)
        if kw['tau'] == 0.0:
            if kw['zf'] is None:
                zmax = pop.zform
            else:
                zmax = kw['zf']
        else:
            zmax = En * (1. + z) / E - 1.
    
        zmax = min(zmax, pop.zform)
    
        # Normalize to help integrator
        Jc = 1e-10
    
        integrand = lambda zu: self.AngleAveragedFluxSlice(z, E, zu,
            tau=0.0) / Jc
    
        flux = quad(integrand, z, zmax,
            epsrel=self._rtol, epsabs=self._atol, limit=self._divmax)[0]    
    
        # Flux in units of photons s^-1 cm^-2 Hz^-1 sr^-1                                        
        flux *= Jc
    
        # Possibly convert to energy flux units
        if kw['energy_units']:
            flux *= E * erg_per_ev
    
        return flux
        
    @property
    def frec(self):
        if not hasattr(self, '_frec'):
            n = np.arange(2, self.pf['lya_nmax'])
            self._frec = np.array(map(self.hydr.frec, n)) 
    
        return self._frec
        
    def LymanAlphaFlux(self, z=None, fluxes=None, popid=0, **kwargs):
        """
        Compute background flux at Lyman-alpha resonance. Includes products
        of Ly-n cascades if approx_lwb=0.
        
        Parameters
        ----------
        z : int, float
            Redshift of interest
        fluxes : np.ndarray
            Results of LWBackground. List of 2-D arrays, one per Ly-n band
            (from n=2 to n=lya_nmax). 

        Returns
        -------
        Lyman alpha flux at given redshift, or, if fluxes are supplied, returns
        flux at all redshifts.
            
        """
        
        pop = self.sources[popid]

        if not self.pf['is_lya_src'] or (z > pop.zform):
            return 0.0

        if self.pf['Ja'] is not None:
            return self.pf['Ja'](z)    

        # Full calculation
        if self.pf['approx_lwb'] == 0:

            if self.pf['discrete_lwb']:
                J = np.zeros(fluxes[0].shape[0])
            else:
                J = 0.0
            
            for i, n in enumerate(np.arange(2, self.pf['lya_nmax'])):
    
                if n == 2 and not self.pf['lya_continuum']:
                    continue
                if n > 2 and not self.pf['lya_injected']:
                    continue
    
                En = self.hydr.ELyn(n)
                Enp1 = self.hydr.ELyn(n + 1)
                
                if self.pf['discrete_lwb']:
                    Jn = self.hydr.frec(n) * fluxes[i][:,0]
                else:
                    Eeval = En + 0.01 * (Enp1 - En)
                    Jn = self.hydr.frec(n) * self.LymanWernerFlux(z, Eeval, 
                        **kwargs)    
    
                J += Jn
    
            return J
    
        # Flat spectrum, no injected photons, instantaneous emission only
        else:
            norm = c * self.cosm.dtdz(z) / four_pi
            return norm * (1. + z)**3 * (1. + self.pf['lya_frec_bar']) * \
                pop.LymanWernerPhotonLuminosityDensity(z) / dnu
        
    def load_sed(self, prefix=None):
        fn = pop.rs.sed_name()
    
        if prefix is None:
            if not ARES:
                print "No $ARES environment variable."
                return None
    
            input_dirs = ['%s/input/seds' % ARES]
    
        else:
            if type(prefix) is str:
                input_dirs = [prefix]
            else:
                input_dirs = prefix
    
        guess = '%s/%s.txt' % (input_dirs[0], fn)
        self.tabname = guess
        if os.path.exists(guess):
            return guess         
    
        pre, tmp2 = fn.split('_logE_')
        post = '_logE_' + tmp2.replace('.txt', '')
    
        good_tab = None
        for input_dir in input_dirs:
            for fn1 in os.listdir(input_dir):
    
                # If source properties are right
                if re.search(pre, fn1):
                    good_tab = '%s/%s' % (input_dir, fn1)    
    
                # If number of redshift bins and energy range right...
                if re.search(pre, fn1) and re.search(post, fn1):
                    good_tab = '%s/%s' % (input_dir, fn1)
                    break
    
        self.tabname = good_tab
        return good_tab

    def TabulateEmissivity(self, z, E, popid=0):
        """
        Tabulate emissivity over photon energy and redshift.
        
        Parameters
        ----------
        E : np.ndarray
            Array of photon energies [eV]
        z : np.ndarray
            Array of redshifts 
        popid : int
            Identification number for population of interest.
            
        Returns
        -------
        A 2-D array, first axis corresponding to redshift, second axis for
        photon energy.
            
        """ 
        
        pop = self.sources[popid]
             
        if np.all(E < E_th[0]):
            L_func = pop.LymanWernerLuminosityDensity
        else:
            L_func = pop.XrayLuminosityDensity
        
        Nz, Nf = len(z), len(E)
        
        Inu = np.zeros(Nf)
        for i in xrange(Nf): 
            Inu[i] = pop.rs.Spectrum(E[i])

        # Convert to photon energy (well, something proportional to it)
        Inu_hat = Inu / E
        
        # Now, redshift dependent parts    
        epsilon = np.zeros([Nz, Nf])                     
        for ll in xrange(Nz):
            H = self.cosm.HubbleParameter(z[ll])                 
            Lbol = L_func(z[ll])  
            epsilon[ll,:] = Inu_hat * Lbol * ev_per_hz / H / erg_per_ev                
        
        return epsilon
            
    def XrayBackground(self):
        """
        Compute Cosmic X-ray Background over all redshifts.
    
        Returns
        -------
        Redshifts, photon energies, and CXB fluxes, (z, E, flux).
        The flux array has shape (# redshift points, # frequency points).
    
        """
    
        # Now, compute background flux
        cxrb = self.XrayFluxGenerator(self.volume.tau)
    
        fluxes = np.zeros([self.volume.L, self.volume.N])
        for i, flux in enumerate(cxrb):
            j = self.volume.L - i - 1  # since we're going from high-z to low-z
            fluxes[j,:] = flux.copy()
    
        return self.volume.z, self.volume.E, fluxes    
    
    def XrayFluxGenerator(self, tau=None, emissivity=None, flux0=None, popid=0):
        """ 
        Compute X-ray background flux in a memory efficient way.
    
        Parameters
        ----------
        tau : np.ndarray
            2-D optical depth, dimensions (self.L, self.N)
        emissivity : np.ndarray
            2-D, dimensions (self.L, self.N)
        flux0 : np.ndarray
            1-D array of fluxes, size is self.N
    
        Notes
        -----
        1. We only tabulate the emissivity in log-x formalism. 
        2. This cannot be parallelized.
          -I suppose we could parallelize over frequency but not redshift,
           but then fluxes would have to be communicated on every redshift
           step. Probably not worth it.
    
        Returns
        -------
        Generator for the flux, each in units of s**-1 cm**-2 Hz**-1 sr**-1
    
        """
    
        if self.pf['redshift_bins'] is None and self.pf['tau_table'] is None:
            raise ValueError('This method only works if redshift_bins != None.')

        if emissivity is None:
            emissivity_over_H = self.TabulateEmissivity(self.volume.z, 
                self.volume.E, popid=popid)
        else:
            emissivity_over_H = emissivity

        if tau is None:
            tau = self.volume.tau

        optically_thin = False
        if np.all(tau == 0):
            optically_thin = True
    
        otf = False
        if tau.shape == self.volume.E.shape:
            otf = True

        if flux0 is None:    
            flux = np.zeros_like(self.volume.E)
        else:
            flux = flux0.copy()

        ll = self.volume.L - 1
        self.tau = tau

        # Loop over redshift - this is the generator                    
        z = self.volume.z[-1]
        while z >= self.volume.z[0]:
            
            # First iteration: no time for there to be flux yet
            # (will use argument flux0 if the EoR just started)
            if ll == (self.volume.L - 1):
                pass
    
            # General case
            else:
                    
                if otf:
                    exp_term = np.exp(-np.roll(tau, -1))
                else:   
                    exp_term = np.exp(-np.roll(tau[ll], -1))
    
                trapz_base = 0.5 * (self.volume.z[ll+1] - self.volume.z[ll])

                # First term in Eq. 25 of Mirocha (2014)
                #fnm1 = np.roll(emissivity_over_H[ll+1], -1, axis=-1)                
                #fnm1 *= exp_term     
                #fnm1 += emissivity_over_H[ll]
                #fnm1 *= trapz_base
                #
                ## Second term in Eq. 25 of Mirocha (2014)       
                #flux = np.roll(flux, -1) * exp_term / self.volume.Rsq
                #
                ## Add two terms together to get final flux
                #flux += fnm1 * c * self.volume.x[ll]**2 / four_pi
    
                # Less readable version, but faster!
                # Equivalent to Eq. 25 in Mirocha (2014)
                flux = (c / four_pi) \
                    * ((self.volume.xsq[ll+1] * trapz_base) \
                    * emissivity_over_H[ll]) \
                    + exp_term * ((c / four_pi) * self.volume.xsq[ll+1] \
                    * trapz_base * np.roll(emissivity_over_H[ll+1], -1, axis=-1) \
                    + np.roll(flux, -1) / self.volume.Rsq)
                
            # No higher energies for photons to redshift from.
            # An alternative would be to extrapolate, and thus mimic a
            # background spectrum that is not truncated at Emax
            flux[-1] = 0.0
    
            yield flux
    
            # Increment redshift
            ll -= 1
            z = self.volume.z[ll]
    
            if ll == -1:
                break
    
    def LWFluxGenerator(self, popid=0):
        """
        Evolute Lyman-Werner background in time.
        
        Returns
        -------
        Generator for the flux, each in units of s**-1 cm**-2 Hz**-1 sr**-1.
        Unlike XrayFluxGenerator, this is a list, with each element 
        corresponding to the flux between n and n+1 resonances.
        """
        
        Nn = len(self.volume.lwb_En)
        
        flux = [np.zeros_like(self.volume.lwb_En[i]) for i in range(Nn)]
        
        L = len(self.volume.lwb_zl)
        ll = L - 1
        
        # Loop over redshift - this is the generator                    
        z = self.volume.lwb_zl[-1]
        while z >= self.volume.lwb_zl[0]:
            
            # Loop over Lyman-n bands
            for i, n in enumerate(self.volume.lwb_n):
                
                # Emissivity in this band, at this redshift, for all energies
                emissivity_over_H = self.volume.lwb_emiss[i][popid]
            
                # First iteration: no time for there to be flux yet
                # (will use argument flux0 if the EoR just started)
                if ll == (L - 1):
                    pass
                
                # General case
                else:
                        
                    trapz_base = 0.5 * \
                        (self.volume.lwb_zl[ll+1] - self.volume.lwb_zl[ll])

                    # Equivalent to Eq. 25 in Mirocha (2014) but tau = 0
                    flux[i] = (c / four_pi) \
                        * ((self.volume.lwb_xsq[ll+1] * trapz_base) \
                        * emissivity_over_H[ll]) \
                        + ((c / four_pi) * self.volume.lwb_xsq[ll+1] \
                        * trapz_base * np.roll(emissivity_over_H[ll+1], -1, axis=-1) \
                        + np.roll(flux[i], -1) / self.volume.lwb_Rsq)
                    
                # This must be corrected: this bin cannot contain photons
                # that originated @ z_{ll+1} because those photons would be 
                # absorbed at the Ly-n+1 resonance, not Ly-n.
                flux[i][-1] = 0.0
        
            yield flux
    
            # Increment redshift
            ll -= 1
            z = self.volume.lwb_zl[ll]
    
            if ll == -1:
                break

    def FluxGenerator(self, tau=None, emissivity=None, flux0=None):
        """
        Evolve some radiation background in time.
    
        Returns
        -------
        Generator for the flux, each in units of s**-1 cm**-2 Hz**-1 sr**-1.
        Unlike XrayFluxGenerator, this is a list, with each element 
        corresponding to the flux between n and n+1 resonances.
        """
    
        Nn = len(self.volume.lwb_En)
    
        flux = [np.zeros_like(self.volume.lwb_En[i]) for i in range(Nn)]
    
        L = len(self.volume.lwb_zl)
        ll = L - 1
    
        # Loop over redshift - this is the generator                    
        z = self.volume.lwb_zl[-1]
        while z >= self.volume.lwb_zl[0]:
    
            # Loop over Lyman-n bands
            for i, n in enumerate(self.volume.lwb_n):
    
                # Emissivity in this band, at this redshift, for all energies
                emissivity_over_H = self.volume.lwb_emiss[i]
    
                # First iteration: no time for there to be flux yet
                # (will use argument flux0 if the EoR just started)
                if ll == (L - 1):
                    pass
    
                # General case
                else:
    
                    trapz_base = 0.5 * \
                        (self.volume.lwb_zl[ll+1] - self.volume.lwb_zl[ll])
    
                    # Equivalent to Eq. 25 in Mirocha (2014) but tau = 0
                    flux[i] = (c / four_pi) \
                        * ((self.volume.lwb_xsq[ll+1] * trapz_base) \
                        * emissivity_over_H[ll]) \
                        + ((c / four_pi) * self.volume.lwb_xsq[ll+1] \
                        * trapz_base * np.roll(emissivity_over_H[ll+1], -1, axis=-1) \
                        + np.roll(flux[i], -1) / self.volume.lwb_Rsq)

                # This must be corrected: this bin cannot contain photons
                # that originated @ z_{ll+1} because those photons would be 
                # absorbed at the Ly-n+1 resonance, not Ly-n.
                flux[i][-1] = 0.0

            yield flux
    
            # Increment redshift
            ll -= 1
            z = self.volume.lwb_zl[ll]
    
            if ll == -1:
                break
    
    