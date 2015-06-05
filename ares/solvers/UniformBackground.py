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
from ..static import GlobalVolume
from ..util.PrintInfo import print_rb
from ..util.Misc import num_freq_bins
from scipy.interpolate import interp1d
from ..physics import Hydrogen, Cosmology
from ..populations import CompositePopulation
from ..util.ReadData import flatten_flux, split_flux
from scipy.integrate import quad, romberg, romb, trapz, simps
from ..physics.Constants import ev_per_hz, erg_per_ev, c, E_LyA, E_LL, dnu

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

bands = ['ir', 'lw', 'uv', 'xr']

class UniformBackground(object):
    def __init__(self, grid=None, **kwargs):
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
            self.grid = grid
            self.cosm = grid.cosm
        else:
            self.grid = None
            self.cosm = Cosmology()

        self._set_sources()
        self._set_generators()
        self._set_integrator()
        
    @property
    def hydr(self):
        if not hasattr(self, '_hydr'):
            self._hydr = Hydrogen(self.cosm, 
                approx_Salpha=self.pf['approx_Salpha'], 
                nmax=self.pf['lya_nmax'])

        return self._hydr

    @property
    def volume(self):
        if not hasattr(self, '_volume'):
            self._volume = GlobalVolume(self)

        return self._volume        

    def _set_sources(self):
        """
        Initialize population(s) of radiation sources!
        
        This routine will figure out emission energies, redshifts, and
        tabulate emissivities. 
        
        Returns
        -------
        Nothing. Sets attributes `energies`, `redshifts`, and `emissivity`
        for each population.
        
        """

        self.sources = CompositePopulation(**self.pf).pops
        self.Ns = self.Nsources = len(self.sources)
        
        self.approx_all_sources = True
        for src in self.sources:
            self.approx_all_sources *= src.approx_src

        # Figure out which band each population emits in
        self.bands = []
        for source in self.sources:

            source_band = []
            for band in bands:
                if source.pf['approx_%sb' % band]:
                    continue

                if source.pf['is_src_%sb' % band]:
                    source_band.append(band)

            if len(source_band) == 0:
                source_band.append(None)
            if len(source_band) > 1:
                raise ValueError('Cannot have source emit in more than 1 band!')

            self.bands.append(source_band[0])
                    
        self.tau = []
        self.energies = []; self.redshifts = []; self.emissivities = []
        for i, source in enumerate(self.sources):
            if self.bands[i] is not None:
                z, nrg = self._set_grid(popid=i)
                    
                # Try to load in optical depth - fix energies and such if found.
                if source.pf['tau_%sb' % self.bands[i]]:
                    z, nrg, tau = self.volume._fetch_tau(i, zpf=z, Epf=nrg)
                else:
                    tau = np.zeros([len(z), len(nrg)])
                
                if self.bands[i] == 'lw':    
                    ehat = [self.TabulateEmissivity(z, Earr, i) for Earr in nrg]
                else:        
                    ehat = self.TabulateEmissivity(z, nrg, i)
            else:
                z = nrg = ehat = None
                tau = None
                
            self.tau.append(tau)
            self.energies.append(nrg)
            self.redshifts.append(z)
            self.emissivities.append(ehat)

    def _set_grid(self, popid=0, band=None, zi=None, zf=None, nz=None, 
        Emin=None, Emax=None):
        """
        Create energy and redshift arrays.
        
        Parameters
        ----------
        
        
        Returns
        -------
        Tuple of redshifts and energies for this particular population.
        
        References
        ----------
        Haardt, F. & Madau, P. 1996, ApJ, 461, 20
        
        """
        
        source = self.sources[popid]
        
        if band is None:
            band = self.bands[popid]
        if zi is None:
            zi = source.pf['initial_redshift']
        if zf is None:    
            zf = source.pf['final_redshift']
        if nz is None:
            nz = source.pf['redshifts_%sb' % band]
        if Emin is None:
            Emin = E0 = source.pf['source_Emin']
        if Emax is None:
            Emax = E1 = source.pf['source_Emax']   
            
        x = np.logspace(np.log10(1 + zf), np.log10(1 + zi), nz)
        z = x - 1.   
        R = x[1] / x[0]          
        
        # Special treatment if LWB or UVB - can concatenate sub-arrays later
        if band in ['lw']:
            energies = []
            narr = np.arange(2, self.pf['lwb_nmax'])
            for n in narr:
                E0 = self.hydr.ELyn(n)
                E1 = self.hydr.ELyn(n + 1)
                
                N = num_freq_bins(nz, zi=zi, zf=zf, Emin=E0, Emax=E1)
                
                # Create energy arrays
                E = E0 * R**np.arange(N)
                
                energies.append(E)
                                                
        else:
            N = num_freq_bins(x.size, zi=zi, zf=zf, Emin=E0, Emax=E1)
            E = energies = E0 * R**np.arange(N)

        return z, energies

    def _set_generators(self):
        """
        Create generators for each population.
        
        Returns
        -------
        Nothing. Sets attribute `generators`.

        """
        
        self.generators = []
        for i, source in enumerate(self.sources):
            if self.bands[i] is None:
                gen = None
            else:
                gen = self.FluxGenerator(popid=i)
            
            self.generators.append(gen)    
            
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
    
    def update_rate_coefficients(self, z, **kwargs):
        """
        Compute ionization and heating rate coefficients.

        Returns
        -------
        Dictionary containing ionization and heating rate coefficients.

        """

        # Setup arrays for results - sorted by sources and absorbers
        # The middle dimension of length 1 is the number of cells
        self.k_ion  = np.zeros([self.Ns, 1, self.grid.N_absorbers])
        self.k_ion2 = np.zeros([self.Ns, 1, self.grid.N_absorbers, 
            self.grid.N_absorbers])
        self.k_heat = np.zeros([self.Ns, 1, self.grid.N_absorbers])
        
        # Loop over sources
        for i, source in enumerate(self.sources):

            # Loop over absorbing species
            for j, species in enumerate(self.grid.absorbers):

                if kwargs['zone'] == 'igm':
                    self.k_ion[i,0,j] = \
                        self.volume.IonizationRateIGM(z, species=j, popid=i,
                        **kwargs)
                    self.k_heat[i,0,j] = \
                        self.volume.HeatingRate(z, species=j, popid=i,
                        **kwargs)

                    for k, donor in enumerate(self.grid.absorbers):
                        self.k_ion2[i,0,j,k] = \
                            self.volume.SecondaryIonizationRateIGM(z, 
                            species=j, donor=k, popid=i, **kwargs)

                else:
                    self.k_ion[i,0,j] = \
                        self.volume.IonizationRateCGM(z, species=j, popid=i,
                        **kwargs)

        # Sum over sources
        self.k_ion_tot = np.sum(self.k_ion, axis=0)
        self.k_ion2_tot = np.sum(self.k_ion2, axis=0)
        self.k_heat_tot = np.sum(self.k_heat, axis=0)

        to_return = \
        {
         'k_ion': self.k_ion_tot,
         'k_ion2': self.k_ion2_tot,
         'k_heat': self.k_heat_tot,
        }

        return to_return

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
        
    @property
    def narr(self):
        if not hasattr(self, '_narr'):
            self._narr = np.arange(2, self.pf['lya_nmax'])    
        
        return self._narr
        
    def LymanAlphaFlux(self, z=None, fluxes=None, popid=0, **kwargs):
        """
        Compute background flux at Lyman-alpha resonance. 
        
        ..note:: Optionally includes products of Ly-n cascades if approx_lwb=0.
        
        Parameters
        ----------
        z : int, float
            Redshift of interest
        fluxes : np.ndarray
            Fluxes grouped by LW band at a single redshift.

        Returns
        -------
        Lyman alpha flux at given redshift.
            
        """
        
        pop = self.sources[popid]

        if not pop.pf['is_lya_src'] or (z > pop.zform):
            return 0.0

        if pop.pf['Ja'] is not None:
            return pop.pf['Ja'](z)    

        # Full calculation
        if pop.pf['approx_lwb'] == 0:

            J = 0.0

            for i, n in enumerate(self.narr):
    
                if n == 2 and not pop.pf['lya_continuum']:
                    continue
                if n > 2 and not pop.pf['lya_injected']:
                    continue
                
                if self.pf['discrete_lwb']:
                    Jn = self.hydr.frec(n) * fluxes[i][0] * 0.2
                else:

                    En = self.hydr.ELyn(n)
                    Enp1 = self.hydr.ELyn(n + 1)
                    
                    Eeval = En + 0.01 * (Enp1 - En)
                    Jn = self.hydr.frec(n) * self.LymanWernerFlux(z, Eeval, 
                        **kwargs)

                J += Jn

            return J
    
        # Flat spectrum, no injected photons, instantaneous emission only
        else:
            norm = c * self.cosm.dtdz(z) / four_pi
            return norm * (1. + z)**3 * (1. + pop.pf['lya_frec_bar']) * \
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
            
    def _flux_generator_generic(self, energies, redshifts, ehat, tau=None,
        flux0=None):
        """
        Generic flux generator.
        
        Parameters
        ----------
        energies : np.ndarray
            1-D array of photon energies
        redshifts : np.ndarray
            1-D array of redshifts
        ehat : np.ndarray
            2-D array of tabulate emissivities.
        tau : np.ndarray
            2-D array of optical depths, or reference to an array that will
            be modified with time.
        flux0 : np.ndarray  
            1-D array of initial flux values.
            
        """
        
        # Some stuff we need
        x = 1. + redshifts
        xsq = x**2
        R = x[1] / x[0]     
        Rsq = R**2
        
        # Shorthand
        zarr = redshifts

        if tau is None:
            tau = np.zeros([redshifts.size, energies.size])

        if flux0 is None:
            flux = np.zeros_like(energies)

        L = redshifts.size
        ll = L - 1
        
        otf = False

        # Loop over redshift - this is the generator                    
        z = redshifts[-1]
        while z >= redshifts[0]:
            
            # First iteration: no time for there to be flux yet
            # (will use argument flux0 if the EoR just started)
            if ll == (L - 1):
                pass
    
            # General case
            else:
                    
                if otf:
                    exp_term = np.exp(-np.roll(tau, -1))
                else:   
                    exp_term = np.exp(-np.roll(tau[ll], -1))
    
                trapz_base = 0.5 * (zarr[ll+1] - zarr[ll])

                # Equivalent to Eq. 25 in Mirocha (2014)
                # Less readable, but faster!
                flux = (c / four_pi) \
                    * ((xsq[ll+1] * trapz_base) * ehat[ll]) \
                    + exp_term * ((c / four_pi) * xsq[ll+1] \
                    * trapz_base * np.roll(ehat[ll+1], -1, axis=-1) \
                    + np.roll(flux, -1) / Rsq)
                
            # No higher energies for photons to redshift from.
            # An alternative would be to extrapolate, and thus mimic a
            # background spectrum that is not truncated at Emax
            flux[-1] = 0.0
                
            yield redshifts[ll], flux, None
    
            # Increment redshift
            ll -= 1
            z = redshifts[ll]
    
            if ll == -1:
                break
                
    def _compute_line_flux(self, fluxes):  
        """
        Compute emission in lines.
        
        ..note:: Includes Ly-a emission only at this point.
        
        Parameters
        ----------
        List of fluxes, 
        """          
        
        line_flux = [np.zeros_like(fluxes[i]) for i in range(len(fluxes))]
        
        # Compute Lyman-alpha flux
        if self.pf['include_H_Lya']:
            line_flux[0][0] += self.LymanAlphaFlux(z=None, fluxes=fluxes)
        
        return line_flux 
        
    def _flux_generator_sawtooth(self, E, z, ehat):
        """
        Create generators for the flux between all Lyman-n bands.
        """

        gens = []
        for i, nrg in enumerate(E):
            gens.append(self._flux_generator_generic(nrg, z, ehat[i]))
        
        # Generator over redshift
        for i in range(z.size):  
            flux = []      
            for gen in gens:
                z, new_flux, garbage = gen.next()                
                flux.append(new_flux)

            # Increment fluxes
            line_flux = self._compute_line_flux(flux)

            yield z, flatten_flux(flux), flatten_flux(line_flux)
        
    def FluxGenerator(self, popid):
        """
        Evolve some radiation background in time.
        
        Parameters
        ----------
        popid : str
            Create flux generator for a single population.
    
        Returns
        -------
        Generator for the flux, each in units of s**-1 cm**-2 Hz**-1 sr**-1.
        Each step returns the current redshift, and the flux as a function of 
        energy at the current redshift.
        
        """

        band = self.bands[popid]

        if band == 'ir':
            raise NotImplemented('no metagalactic IR background yet.')
    
        elif band == 'lw':
            return self._flux_generator_sawtooth(E=self.energies[popid],
                z=self.redshifts[popid], ehat=self.emissivities[popid])
        elif band == 'uv':
            raise NotImplemented('no metagalactic UV background yet.')    
            
        elif band == 'xr':
            return self._flux_generator_generic(self.energies[popid],
                self.redshifts[popid], self.emissivities[popid],
                tau=self.tau[popid])
                
        
    
