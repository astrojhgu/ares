"""

IntergalacticMedium.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Fri May 24 11:31:06 2013

Description: 

"""

import numpy as np
from ..util.Warnings import *
from ..util import ProgressBar
from ..util import ParameterFile
from ..physics.Constants import *
import types, os, re, sys, pickle
from ..util.Misc import num_freq_bins
from ..physics import SecondaryElectrons
from ..util.Warnings import tau_tab_z_mismatch, no_tau_table
from scipy.integrate import dblquad, romb, simps, quad, trapz

try:
    import h5py
    have_h5py = True    
except ImportError:
    have_h5py = False

try:
    from mpi4py import MPI
    rank = MPI.COMM_WORLD.rank
    size = MPI.COMM_WORLD.size
except ImportError:
    rank = 0
    size = 1

log10 = np.log(10.)
E_th = np.array([13.6, 24.4, 54.4])

defkwargs = \
{
 'zf':None, 
 'xray_flux':None, 
 'epsilon_X': None,
 'Gamma': None,
 'gamma': None,
 'return_rc': False, 
 'energy_units':False, 
 'Emax': None,
 #'zxavg':0.0,
 #'igm':True,
 'xavg': 0.0,
 'igm_h_1': 1.0,
 'igm_h_2': 0.0,
 'igm_he_2': 0.0,
 'igm_he_3': 0.0,
 'cgm_h_1': 1.0,
 'cgm_h_2': 0.0,
 'cgm_he_2': 0.0,
 'cgm_he_3': 0.0,
 'igm_e': 0.0,
}

species_i_to_str = {0:'h_1', 1:'he_1', 2:'he_2'}

tiny_dlogx = 1e-8

class GlobalVolume(object):
    def __init__(self, background, use_tab=True):
        """
        Initialize an inter-galactic medium (IGM) object.
        
        Parameters
        ----------
        background : ares.solvers.UniformBackground instance.
        use_tab : bool
            Use optical depth table? Simulation class will set use_tab=False
            once the EoR begins, at which time the optical depth will be
            computed on-the-fly.
        
        """
        
        self.background = background
        self.pf = background.pf
        self.grid = background.grid
        self.cosm = background.cosm
        self.hydr = background.hydr
        self.sources = background.sources
        self.Ns = len(self.sources)
        
        # Include helium opacities approximately?
        self.approx_He = self.pf['include_He'] and self.pf['approx_He']
        
        # Include helium opacities self-consistently?
        self.self_consistent_He = self.pf['include_He'] \
            and (not self.pf['approx_He'])

        self.esec = \
            SecondaryElectrons(method=self.pf["secondary_ionization"])  

        # Choose function for computing bound-free absorption cross-sections                
        if self.pf['approx_sigma']:
            from ..physics.CrossSections import \
                ApproximatePhotoIonizationCrossSection as sigma
        else:
            from ..physics.CrossSections import \
                PhotoIonizationCrossSection as sigma

        self.sigma = sigma
        self.sigma0 = sigma(E_th[0])    # Hydrogen ionization threshold

        self._set_lwb()
        self._set_xrb(use_tab=use_tab)

        self._set_integrator()

    @property
    def rates_no_RT(self):
        if not hasattr(self, '_rates_no_RT'):
            self._rates_no_RT = \
                {'k_ion': np.zeros((self.Ns, self.grid.dims, 
                    self.grid.N_absorbers)),
                 'k_heat': np.zeros((self.Ns, self.grid.dims, 
                    self.grid.N_absorbers)),
                 'k_ion2': np.zeros((self.Ns, self.grid.dims, 
                    self.grid.N_absorbers, self.grid.N_absorbers)),
                }
    
        return self._rates_no_RT

    def _set_lwb(self):
        """
        Initialize grids for discrete integration of LW Background.
        """
        
        if self.background.approx_all_lwb:
            return
            
        zi = self.pf['initial_redshift']
        zf = self.pf['final_redshift']
        nmax = self.pf['lya_nmax']
        
        Nz = 1e4
        x = np.logspace(np.log10(1 + zf), np.log10(1 + zi), Nz)

        self.lwb_zl = z = x - 1.
        
        logx = np.log10(x)
        logz = np.log10(z)

        # Constant ratio between elements in x-grid
        R = x[1] / x[0]
        logR = np.log10(R)
        
        self.lwb_Rsq = R**2
        self.lwb_xsq = x**2
        
        n_horizon = lambda n: (1. - (n + 1.)**-2.) / (1. - n**-2.)

        self.lwb_n = np.arange(2, nmax)
        self.lwb_E = []
        self.lwb_En = []
        self.lwb_emiss = []     
        for n in self.lwb_n:
            E1 = self.hydr.ELyn(n)
            E2 = self.hydr.ELyn(n + 1)

            Nf = num_freq_bins(Nz, zi=zi, zf=zf, Emin=E1, Emax=E2)

            # Create energy arrays
            E = E1 * R**np.arange(Nf)
            
            # Tabulate emissivity for each source
            ehat = []
            for i, source in enumerate(self.background.sources):
                if not source.pf['is_lya_src']:
                    ehat.append(None)
                    continue
                if source.pf['spectrum_Emin'] > 13.6:
                    ehat.append(None)
                    continue
                
                ehat.append(self.background.TabulateEmissivity(z, E, i))    
            
            self.lwb_E.extend(E)
            self.lwb_En.append(E)
            self.lwb_emiss.append(ehat)
        
        self.lwb_E = np.array(self.lwb_E)    
            
    def _set_xrb(self, use_tab=True):
        """
        From parameter file, initialize grids in redshift and frequency.
        
        Parameters
        ----------
        Only depends on contents of self.pf.
        
        Notes
        -----
        If redshift_bins != None, will setup logarithmic grid in new parameter
        x = 1 + z. Then, given that R = x_{j+1} / x_j = const. for j < J, we can 
        create a logarithmic photon frequency / energy grid. This technique
        is outlined in Haardt & Madau (1996) Appendix C.
        
        References
        ----------
        Haardt, F. & Madau, P. 1996, ApJ, 461, 20
        
        """
        
        if self.background.approx_all_xrb:
            return
        
        if self.pf['redshift_bins'] is None and self.pf['tau_table'] is None:
            
            # Set bounds in frequency/energy space
            self.E0 = self.pf['spectrum_Emin']
            self.E1 = self.pf['spectrum_Emax']    
            
            return
        
        self.tabname = None

        # Use Haardt & Madau (1996) Appendix C technique for z, nu grids
        if not ((self.pf['redshift_bins'] is not None or \
            self.pf['tau_table'] is not None) and (not self.pf['approx_xrb'])):
              
            raise NotImplemented('whats going on here')

        if use_tab and (self.pf['tau_table'] is not None or self.pf['discrete_xrb']):
                            
            found = False
            if self.pf['discrete_xrb']:
                
                # First, look in CWD or $ARES (if it exists)
                self.tabname = self.load_tau(self.pf['tau_prefix'])
                
                if self.tabname is not None:
                    found = True
            
            # tau_table will override any tables found automatically    
            if self.pf['tau_table'] is not None:
                self.tabname = self.pf['tau_table']
            elif found:
                pass
            else:
                # Raise an error if we haven't found anything
                no_tau_table(self)
                sys.exit(1)

            # If we made it this far, we found a table that may be suitable
            self.read_tau(self.tabname)
        
            zmax_ok = (self.z.max() >= self.pf['initial_redshift']) or \
                np.allclose(self.z.max(), self.pf['initial_redshift']) or \
                (self.z.max() >= self.pf['first_light_redshift']) or \
                np.allclose(self.z.max(), self.pf['first_light_redshift'])
                
            zmin_ok = (self.z.min() <= self.pf['final_redshift']) or \
                np.allclose(self.z.min(), self.pf['final_redshift'])
                                    
            Emin_ok = (self.E0 <= self.pf['spectrum_Emin']) or \
                np.allclose(self.E0, self.pf['spectrum_Emin'])
            
            # Results insensitive to Emax (so long as its relatively large)
            # so be lenient with this condition (100 eV or 1% difference
            # between parameter file and lookup table)
            Emax_ok = np.allclose(self.E1, self.pf['spectrum_Emax'],
                atol=100., rtol=1e-2)
                
            # Check redshift bounds
            if not (zmax_ok and zmin_ok):
                if not zmax_ok:
                    tau_tab_z_mismatch(self, zmin_ok, zmax_ok)
                    sys.exit(1)
                else:
                    if self.pf['verbose']:
                        tau_tab_z_mismatch(self, zmin_ok, zmax_ok)
            
            if not (Emax_ok and Emin_ok):
                if self.pf['verbose']:
                    tau_tab_E_mismatch(self, Emin_ok, Emax_ok)
                    
                if self.E1 < self.pf['spectrum_Emax']:
                    sys.exit(1)
                          
            dlogx = np.diff(self.logx)
            if not np.all(np.abs(dlogx - np.roll(dlogx, -1)) <= tiny_dlogx):
                raise ValueError(wrong_tab_type)

        else:
            
            # Set bounds in frequency/energy space
            self.E0 = self.pf['spectrum_Emin']
            self.E1 = self.pf['spectrum_Emax']
            
            # Set up log-grid in parameter x = 1 + z
            self.x = np.logspace(np.log10(1+self.pf['final_redshift']),
                np.log10(1+self.pf['initial_redshift']),
                int(self.pf['redshift_bins']))
                    
            self.z = self.x - 1.
            self.logx = np.log10(self.x)
            self.logz = np.log10(self.z)
        
            # Constant ratio between elements in x-grid
            self.R = self.x[1] / self.x[0]
            self.logR = np.log10(self.R)
            
            # Create mapping to frequency space
            self.N = num_freq_bins(self.x.size, 
                zi=self.pf['initial_redshift'], zf=self.pf['final_redshift'], 
                Emin=self.E0, Emax=self.E1)
            
            # Create energy arrays
            self.E = self.E0 * self.R**np.arange(self.N)
        
        # Frequency grid must be index-1-based.
        self.nn = np.arange(1, self.N+1)
        
        # R-squared and x-squared (crop up in CXRB calculation)
        self.Rsq = self.R**2
        self.xsq = self.x**2
        
        # Set attributes for z-dimensions of optical depth grid
        self.L = self.M = len(self.x)
        self.ll = self.mm = np.arange(self.L)
                    
        self.logE = np.log10(self.E)
        
        self.n0 = min(self.nn)
        self.dE = np.diff(self.E)
        self.dlogE = np.diff(self.logE)
                        
        # Pre-compute cross-sections
        self.sigma_E = np.array([np.array(map(lambda E: self.sigma(E, i), 
            self.E)) for i in xrange(3)])
        self.log_sigma_E = np.log10(self.sigma_E)
        
        # Pre-compute secondary ionization and heating factors
        if self.esec.Method > 1:
            
            self.i_x = 0
            self.fheat = np.ones([self.N, len(self.esec.x)])
            self.flya = np.ones([self.N, len(self.esec.x)])
            
            self.fion = {}
            
            self.fion['h_1'] = np.ones([self.N, len(self.esec.x)])
                        
            # Must evaluate at ELECTRON energy, not photon energy
            for i, E in enumerate(self.E - E_th[0]):
                self.fheat[i,:] = self.esec.DepositionFraction(self.esec.x, 
                    E=E, channel='heat')
                self.fion['h_1'][i,:] = \
                    self.esec.DepositionFraction(self.esec.x, 
                        E=E, channel='h_1')
                        
                if self.pf['secondary_lya']:
                    self.flya[i,:] = self.esec.DepositionFraction(self.esec.x, 
                        E=E, channel='lya') 
                    
            # Helium
            if self.pf['include_He'] and not self.pf['approx_He']:
                
                self.fion['he_1'] = np.ones([self.N, len(self.esec.x)])
                self.fion['he_2'] = np.ones([self.N, len(self.esec.x)])
                
                for i, E in enumerate(self.E - E_th[1]):
                    self.fion['he_1'][i,:] = \
                        self.esec.DepositionFraction(self.esec.x, 
                        E=E, channel='he_1')
                
                for i, E in enumerate(self.E - E_th[2]):
                    self.fion['he_2'][i,:] = \
                        self.esec.DepositionFraction(self.esec.x, 
                        E=E, channel='he_2')            
                        
            
    def _set_integrator(self):
        self.integrator = self.pf["unsampled_integrator"]
        self.sampled_integrator = self.pf["sampled_integrator"]
        self.rtol = self.pf["integrator_rtol"]
        self.atol = self.pf["integrator_atol"]
        self.divmax = int(self.pf["integrator_divmax"])
    
    def read_tau(self, fn):
        """
        Read optical depth table.
        """
        
        if type(fn) is dict:
            
            self.E0 = fn['E'].min()
            self.E1 = fn['E'].max()
            self.E = fn['E']
            self.z = fn['z']
            self.x = self.z + 1
            self.N = self.E.size

            self.R = self.x[1] / self.x[0]

            self.tau = fn['tau']

        elif re.search('hdf5', fn):

            f = h5py.File(self.tabname, 'r')

            self.E0 = min(f['photon_energy'].value)
            self.E1 = max(f['photon_energy'].value)
            self.E = f['photon_energy'].value
            self.z = f['redshift'].value
            self.x = self.z + 1
            self.N = self.E.size

            self.R = self.x[1] / self.x[0]

            self.tau = self._tau = f['tau'].value
            f.close()

        elif re.search('npz', fn) or re.search('pkl', fn):    

            if re.search('pkl', fn):
                f = open(fn, 'rb')
                data = pickle.load(f)
            else:
                f = open(fn, 'r')
                data = dict(np.load(f))
            
            self.E0 = data['E'].min()
            self.E1 = data['E'].max()            
            self.E = data['E']
            self.z = data['z']
            self.x = self.z + 1
            self.N = self.E.size
            
            self.R = self.x[1] / self.x[0]
            
            self.tau = self._tau = data['tau']
            f.close()
            
        else:
            f = open(self.tabname, 'r')
            hdr = f.readline().split()[1:]
            
            tmp = []
            for element in hdr:
                tmp.append(float(element[element.rfind('=')+1:]))

            zmin, zmax, self.E0, self.E1 = tmp

            self.tau = self._tau = np.loadtxt(self.tabname)
            self.N = self.tau.shape[1]
            
            self.x = np.logspace(np.log10(1+zmin), np.log10(1.+zmax),
                int(self.tau.shape[0]))

            self.z = self.x - 1.
            self.E = np.logspace(np.log10(self.E0), np.log10(self.E1), self.N)
                        
        # Correct for inconsistencies between parameter file and table
        if self.pf['spectrum_Emin'] > self.E0:
            Ediff = self.E - self.pf['spectrum_Emin']
            i_E0 = np.argmin(np.abs(Ediff))
            if Ediff[i_E0] < 0:
                i_E0 += 1

            self.tau[:,0:i_E0] = np.inf
        
        if self.pf['spectrum_Emax'] < self.E1:
            Ediff = self.E - self.pf['spectrum_Emax']
            i_E0 = np.argmin(np.abs(Ediff))
            if Ediff[i_E0] < 0:
                i_E0 += 1

            self.tau[:,i_E0+1:] = np.inf

        self.logx = np.log10(self.x)
        self.logz = np.log10(self.z)
    
    def tau_name(self, suffix='hdf5'):
        """
        Return name of table based on its properties.
        """

        if not have_h5py:
            suffix == 'pkl'

        HorHe = 'He' if self.pf['include_He'] else 'H'

        zf = self.pf['final_redshift']
        zi = self.pf['initial_redshift']

        L, N = self.tau_shape()

        E0 = self.pf['spectrum_Emin']
        E1 = self.pf['spectrum_Emax']

        fn = lambda z1, z2, E1, E2: \
            'optical_depth_%s_%ix%i_z_%i-%i_logE_%.2g-%.2g.%s' \
            % (HorHe, L, N, z1, z2, E1, E2, suffix)

        return fn(zf, zi, np.log10(E0), np.log10(E1)), fn
    
    def load_tau(self, prefix=None):
        """
        Find an optical depth table.
        """
        
        fn, fn_func = self.tau_name()
    
        if prefix is None:
            ares_dir = os.environ.get('ARES')
            if not ares_dir:
                print "No ARES environment variable."
                return None
            
            input_dirs = ['%s/input/optical_depth' % ares_dir]
    
        else:
            if type(prefix) is str:
                input_dirs = [prefix]
            else:
                input_dirs = prefix
    
        guess = '%s/%s' % (input_dirs[0], fn)
        if os.path.exists(guess):
            return guess
    
        ## Find exactly what table should be
        zmin, zmax, Nz, lEmin, lEmax, chem, pre, post = self._parse_tab(fn)

        ok_matches = []
        perfect_matches = []
        
        # Loop through input directories
        for input_dir in input_dirs:
                            
            # Loop over files in input_dir, look for best match
            for fn1 in os.listdir(input_dir):
                
                if re.search('hdf5', fn1) and (not have_h5py):
                    continue

                tab_name = '%s/%s' % (input_dir, fn1)
                
                try:
                    zmin_f, zmax_f, Nz_f, lEmin_f, lEmax_f, chem_f, p1, p2 = \
                        self._parse_tab(fn1)
                except:
                    continue

                # Dealbreakers
                if Nz_f != Nz:
                    continue
                if zmax_f < zmax:
                    continue
                if chem_f != chem:
                    continue

                # Continue with possible matches
                for fmt in ['pkl', 'npz', 'hdf5']:

                    if fn1 == fn and fmt == self.pf['preferred_format']:
                        perfect_matches.append(tab_name)
                        continue

                    if c and fmt == self.pf['preferred_format']:
                        perfect_matches.append(tab_name)
                        continue

                    # If number of redshift bins and energy range right...
                    if re.search(pre, fn1) and re.search(post, fn1):
                        if re.search(fmt, fn1) and fmt == self.pf['preferred_format']:
                            perfect_matches.append(tab_name)
                        else:
                            ok_matches.append(tab_name)
                    
                    # If number of redshift bins is right...
                    elif re.search(pre, fn1):
                                                
                        if re.search(fmt, fn1) and fmt == self.pf['preferred_format']:
                            perfect_matches.append(tab_name)
                        else:
                            ok_matches.append(tab_name)
        
        if perfect_matches:
            return perfect_matches[0]
        elif ok_matches:
            return ok_matches[0]
        else:
            return None
            
    def _parse_tab(self, fn):
                
        tmp1, tmp2 = fn.split('_z_')
        pre = tmp1[0:tmp1.rfind('x')]
        red, tmp3 = fn.split('_logE_')
        post = '_logE_' + tmp3.replace('.hdf5', '')
        
        # Find exactly what table should be
        zmin, zmax = map(float, red[red.rfind('z')+2:].partition('-')[0::2])
        logEmin, logEmax = map(float, tmp3[tmp3.rfind('E')+1:tmp3.rfind('.')].partition('-')[0::2])
        
        Nz = pre[pre.rfind('_')+1:]
        
        # Hack off Nz string and optical_depth_
        chem = pre.strip(Nz)[14:-1]#.strip('optical_depth_')
        
        return zmin, zmax, int(Nz), logEmin, logEmax, chem, pre, post
                
    def tau_shape(self):
        """
        Determine dimensions of optical depth table.
        
        Unfortunately, this is a bit redundant with the procedure in
        self._init_xrb, but that's the way it goes.
        """
        
        # Set up log-grid in parameter x = 1 + z
        x = np.logspace(np.log10(1+self.pf['final_redshift']),
            np.log10(1+self.pf['initial_redshift']),
            int(self.pf['redshift_bins']))
        z = x - 1.
        logx = np.log10(x)
        logz = np.log10(z)

        # Constant ratio between elements in x-grid
        R = x[1] / x[0]
        logR = np.log10(R)
        
        E0 = self.pf['spectrum_Emin']
        
        # Create mapping to frequency space
        E = 1. * E0
        n = 1
        while E < self.pf['spectrum_Emax']:
            E = E0 * R**(n - 1)
            n += 1    
        
        # Set attributes for dimensions of optical depth grid
        L = len(x)
        
        # Frequency grid must be index 1-based.
        N = num_freq_bins(L, zi=self.pf['initial_redshift'], 
            zf=self.pf['final_redshift'], Emin=E0, 
            Emax=self.pf['spectrum_Emax'])
        N -= 1
        
        return L, N
    
    def RestFrameEnergy(self, z, E, zp):
        """
        Return energy of a photon observed at (z, E) and emitted at zp.
        """
        
        return E * (1. + zp) / (1. + z)
    
    def ObserverFrameEnergy(self, z, Ep, zp):
        """
        What is the energy of a photon observed at redshift z and emitted 
        at redshift zp and energy Ep?
        """
        
        return Ep * (1. + z) / (1. + zp)
        
    def Jc(self, z, E):
        """
        Flux corresponding to one photon per hydrogen atom at redshift z.
        """
        
        return c * self.cosm.nH0 * (1. + z)**3 / 4. / np.pi \
            / (E * erg_per_ev / h)
         
    def rate_to_coefficient(self, z, species=0, **kw):
        """
        Convert an ionization/heating rate to a rate coefficient.
        
        Provides units of per atom.
        """
        if species == 0:     
            weight = 1. / self.cosm.nH(z) / kw['igm_h_1']
        elif species == 1:
            weight = 1. / self.cosm.nHe(z) / kw['igm_he_1']
        elif species == 2:
            weight = 1. / self.cosm.nHe(z) / kw['igm_he_2']
         
        return weight
        
    def coefficient_to_rate(self, z, species=0, **kw):
        return 1. / self.rate_to_coefficient(z, species, **kw)
        
    def _fix_kwargs(self, functionify=False, popid=0, **kwargs):
        
        kw = defkwargs.copy()
        kw.update(kwargs)
        
        pop = self.sources[popid]
        
        if functionify and type(kw['xavg']) is not types.FunctionType:
            tmp = kw['xavg']
            kw['xavg'] = lambda z: tmp
        
        if kw['zf'] is None and pop is not None:
            kw['zf'] = pop.zform
        
        if kw['Emax'] is None and (not self.pf['approx_xrb']):
            kw['Emax'] = self.E1    
            
        return kw
        
    def HeatingRate(self, z, species=0, popid=0, **kwargs):
        """
        Compute heating rate density due to emission from this population. 
        
        Parameters
        ----------
        z : int, float
            Redshift of interest.
        species : int
            Atom whose liberated electrons cause heating.
            Can be 0, 1, or 2 (HI, HeI, and HeII, respectively)
        
        ===============
        relevant kwargs
        ===============
        xray_flux : np.ndarray
            Array of fluxes corresponding to photon energies in self.igm.E.
        return_rc : bool
            Return actual heating rate, or rate coefficient for heating?
            Former has units of erg s**-1 cm**-3, latter has units of 
            erg s**-1 cm**-3 atom**-1.    
        
        Returns
        -------
        Proper heating rate density in units of in erg s**-1 cm**-3 at redshift z,
        due to electrons previously bound to input species.

        """
                
        pop = self.sources[popid]        
                                
        if not self.pf['is_heat_src_igm'] or (z >= pop.zform):
            return 0.0
        
        # Grab defaults, do some patches if need be    
        kw = self._fix_kwargs(**kwargs)
                        
        # Return right away if heating rate density is parameterized
        if self.pf['heat_igm'] is not None:
            return self.pf['heat_igm'](z) 

        # Compute fraction of photo-electron energy deposited as heat
        if self.pf['fXh'] is None:
            if self.esec.Method > 1 and (not self.pf['approx_xrb']) \
                and (kw['xray_flux'] is not None):
                if kw['igm_h_2'] == 0:
                    fheat = self.fheat[:,0]
                else:
                    if kw['igm_h_2'] > self.esec.x[self.i_x + 1]:
                        self.i_x += 1
                    
                    j = self.i_x + 1
                    
                    fheat = self.fheat[:,self.i_x] \
                        + (self.fheat[:,j] - self.fheat[:,self.i_x]) \
                        * (kw['igm_h_2'] - self.esec.x[self.i_x]) \
                        / (self.esec.x[j] - self.esec.x[self.i_x])                
            else:
                fheat = self.esec.DepositionFraction(kw['igm_h_2'])[0]
        else:
            fheat = self.pf['fXh']
            
        # Assume heating rate density at redshift z is only due to emission
        # from sources at redshift z
        if self.pf['approx_xrb']:
            weight = self.rate_to_coefficient(z, species, **kw)
            L = pop.XrayLuminosityDensity(z) # erg / s / c-cm**3

            return weight * fheat * L * (1. + z)**3
            
        # Otherwise, do the full calculation
                
        # Re-normalize to help integrator
        norm = J21_num * self.sigma0
                
        # Computes excess photo-electron energy due to ionizations by
        # photons with energy E (normalized by sigma0 * Jhat)
        if kw['xray_flux'] is None:

            # If we're approximating helium, must add contributions now
            # since we'll never explicitly call this method w/ species=1.
            if self.approx_He:
                integrand = lambda E, zz: \
                    self.rb.AngleAveragedFluxSlice(z, E, zz, xavg=kw['xavg']) \
                    * (self.sigma(E) * (E - E_th[0]) \
                    + self.cosm.y * self.sigma(E, species=1) * (E - E_th[1])) \
                    * fheat / norm / ev_per_hz
                    
            # Otherwise, just heating via hydrogen photo-electrons
            else:
                integrand = lambda E, zz: \
                    self.rb.AngleAveragedFluxSlice(z, E, zz, xavg=kw['xavg'], 
                    zxavg=kw['zxavg']) * self.sigma(E, species=1) \
                    * (E - E_th[species]) * fheat / norm / ev_per_hz
        
        # This means the fluxes have been computed already - integrate
        # over discrete set of points
        else:

            integrand = self.sigma_E[species] * (self.E - E_th[species])

            if self.approx_He:
                integrand += self.cosm.y * self.sigma_E[1] \
                    * (self.E - E_th[1])

            integrand *= kw['xray_flux'] * fheat / norm / ev_per_hz
                         
        # Compute integral over energy
        if type(integrand) == types.FunctionType:
            heat, err = dblquad(integrand, z, kw['zf'], lambda a: self.E0, 
                lambda b: kw['Emax'], epsrel=self.rtol, epsabs=self.atol)
        else:
            if kw['Emax'] is not None:
                imax = np.argmin(np.abs(self.E - kw['Emax']))
                if imax == 0:
                    return 0.0
                    
                if self.sampled_integrator == 'romb':
                    raise ValueError("Romberg's method cannot be used for integrating subintervals.")
                    heat = romb(integrand[0:imax] * self.E[0:imax], dx=self.dlogE[0:imax])[0] * log10
                else:
                    heat = simps(integrand[0:imax] * self.E[0:imax], x=self.logE[0:imax]) * log10
            
            else:
                imin = np.argmin(np.abs(self.E - pop.pf['spectrum_Emin']))
                
                if self.sampled_integrator == 'romb':
                    heat = romb(integrand[imin:] * self.E[imin:], 
                        dx=self.dlogE[imin:])[0] * log10
                elif self.sampled_integrator == 'trapz':
                    heat = np.trapz(integrand[imin:] * self.E[imin:], 
                        x=self.logE[imin:]) * log10
                else:
                    heat = simps(integrand[imin:] * self.E[imin:], 
                        x=self.logE[imin:]) * log10
          
        # Re-normalize, get rid of per steradian units
        heat *= 4. * np.pi * norm * erg_per_ev

        # Currently a rate coefficient, returned value depends on return_rc                                      
        if kw['return_rc']:
            pass
        else:
            heat *= self.coefficient_to_rate(z, species, **kw)

        return heat    
        
    def IonizationRateCGM(self, z, species=0, popid=0, **kwargs):
        """
        Compute volume averaged hydrogen ionization rate.

        Parameters
        ----------
        z : float
            current redshift
        species : int
            Ionization rate for what atom?
            Can be 0, 1, or 2 (HI, HeI, and HeII, respectively)
            
        ===============
        relevant kwargs
        ===============
        xray_flux : np.ndarray
            Array of fluxes corresponding to photon energies in self.igm.E.
        return_rc : bool
            Return actual heating rate, or rate coefficient for heating?
            Former has units of erg s**-1 cm**-3, latter has units of 
            erg s**-1 cm**-3 atom**-1.    

        Returns
        -------
        Ionization rate. Units determined by value of return_rc keyword
        argument, which is False by default.

        """
        
        pop = self.sources[popid]
        
        if (not self.pf['is_ion_src_cgm']) or (z > pop.zform):
            return 0.0
            
        # Need some guidance from 1-D calculations to do this
        if species > 0:
            return 0.0
        
        kw = defkwargs.copy()
        kw.update(kwargs)

        if self.pf['Gamma_cgm'] is not None:
            return self.pf['Gamma_cgm'](z)
                
        if kw['return_rc']:
            weight = self.rate_to_coefficient(z, species, **kw)
        else:
            weight = 1.0

        return weight \
            * pop.IonizingPhotonLuminosityDensity(z) * (1. + z)**3
    
    def IonizationRateIGM(self, z, species=0, popid=0, **kwargs):
        """
        Compute volume averaged hydrogen ionization rate.
        
        Parameters
        ----------
        z : float
            redshift
        species : int
            HI, HeI, or HeII (species=0, 1, 2, respectively)
            
        Returns
        -------
        Volume averaged ionization rate in units of ionizations per 
        second. If return_rc=True, will be in units of ionizations per
        second per atom.
        
        """
        
        pop = self.sources[popid]                     
                                
        # z between zform, zdead? must be careful for BHs
        if (not self.pf['is_ion_src_igm']) or (z > pop.zform):
            return 0.0
                
        # Grab defaults, do some patches if need be            
        kw = self._fix_kwargs(**kwargs)
                        
        if self.pf['Gamma_igm'] is not None:
            return self.pf['Gamma_igm'](z, species, **kw)

        if self.pf['approx_xrb']:
            weight = self.rate_to_coefficient(z, species, **kw)
            primary = weight * pop.XrayLuminosityDensity(z) \
                * (1. + z)**3 / pop.pf['xray_Eavg'] / erg_per_ev
            fion = self.esec.DepositionFraction(kw['igm_h_2'], channel='h_1')[0]

            return primary * (1. + fion) * (pop.pf['xray_Eavg'] - E_th[0]) \
                / E_th[0]

        # Full calculation - much like computing integrated flux
        norm = J21_num * self.sigma0
        
        # Integrate over function
        if kw['xray_flux'] is None:
            integrand = lambda E, zz: \
                self.rb.AngleAveragedFluxSlice(z, E, zz, xavg=kw['xavg'], 
                zxavg=kw['zxavg']) * self.sigma(E, species=species) \
                / norm / ev_per_hz
                
            ion, err = dblquad(integrand, z, kw['zf'], lambda a: self.E0, 
                lambda b: kw['Emax'], epsrel=self.rtol, epsabs=self.atol)    
        
        # Integrate over set of discrete points
        else:  
            integrand = self.sigma_E[species] \
                * kw['xray_flux'] / norm / ev_per_hz
        
            if self.sampled_integrator == 'romb':
                ion = romb(integrand * self.E, dx=self.dlogE)[0] * log10
            else:
                ion = simps(integrand * self.E, x=self.logE) * log10
                
        # Re-normalize
        ion *= 4. * np.pi * norm
        
        # Currently a rate coefficient, returned value depends on return_rc
        if kw['return_rc']:
            pass
        else:
            ion *= self.coefficient_to_rate(z, species, **kw) 
        
        return ion
                
    def SecondaryIonizationRateIGM(self, z, species=0, donor=0, **kwargs):
        """
        Compute volume averaged secondary ionization rate.

        Parameters
        ----------
        z : float
            redshift
        species : int
            Ionization rate of what atom?
            Can be 0, 1, or 2 (HI, HeI, and HeII, respectively)
        donor : int
            Which atom gave the electron?
            Can be 0, 1, or 2 (HI, HeI, and HeII, respectively)        

        ===============
        relevant kwargs
        ===============
        xray_flux : np.ndarray
            Array of fluxes corresponding to photon energies in self.igm.E.
        return_rc : bool
            Return actual heating rate, or rate coefficient for heating?
            Former has units of erg s**-1 cm**-3, latter has units of 
            erg s**-1 cm**-3 atom**-1.    

        Returns
        -------
        Volume averaged ionization rate due to secondary electrons, 
        in units of ionizations per second.

        """               

        if self.pf['secondary_ionization'] == 0:
            return 0.0

        # Computed in IonizationRateIGM in this case
        if self.pf['approx_xrb']:
            return 0.0

        if not self.rb.pf['is_ion_src_igm']:
            return 0.0 
            
        if ((donor or species) in [1,2]) and self.pf['approx_He']:
            return 0.0

        # Grab defaults, do some patches if need be
        kw = self._fix_kwargs(**kwargs)

        if self.pf['gamma_igm'] is not None:
            return self.pf['gamma_igm'](z)
            
        species_str = species_i_to_str[species]
        donor_str = species_i_to_str[donor]

        if self.esec.Method > 1:
            fion_const = 1.
            if kw['igm_e'] == 0:
                fion = self.fion[species_str][:,0]
            else:
                if kw['igm_e'] > self.esec.x[self.i_x + 1]:
                    self.i_x += 1

                j = self.i_x + 1

                fion = self.fion[species_str][:,self.i_x] \
                    + (self.fion[species_str][:,j] - self.fion[species_str][:,self.i_x]) \
                    * (kw['igm_e'] - self.esec.x[self.i_x]) \
                    / (self.esec.x[j] - self.esec.x[self.i_x])
        else:
            fion = 1.0
            fion_const = self.esec.DepositionFraction(kw['igm_e'], 
                channel=species_str)[0]

        norm = J21_num * self.sigma0
                                
        if kw['xray_flux'] is None:        
            if self.pf['approx_He']: # assumes lower integration limit > 4 Ryd
                integrand = lambda E, zz: \
                    self.rb.AngleAveragedFluxSlice(z, E, zz, xavg=kw['xavg'], 
                    zxavg=kw['zxavg']) * (self.sigma(E) * (E - E_th[0]) \
                    + self.cosm.y * self.sigma(E, 1) * (E - E_th[1])) \
                    / E_th[0] / norm / ev_per_hz
            else:
                integrand = lambda E, zz: \
                    self.rb.AngleAveragedFluxSlice(z, E, zz, xavg=kw['xavg'], 
                    zxavg=kw['zxavg']) * self.sigma(E) * (E - E_th[0]) \
                    / E_th[0] / norm / ev_per_hz
        else:
            integrand = fion * self.sigma_E[donor] * (self.E - E_th[donor])
            
            if self.pf['approx_He']:
                integrand += self.cosm.y * self.sigma_E[1] \
                    * (self.E - E_th[1])
            
            integrand = integrand
            integrand *= kw['xray_flux'] / E_th[species] / norm / ev_per_hz
        
        if type(integrand) == types.FunctionType:
            ion, err = dblquad(integrand, z, kw['zf'], lambda a: self.E0, 
                lambda b: kw['Emax'], epsrel=self.rtol, epsabs=self.atol)
        else:
            if self.sampled_integrator == 'romb':
                ion = romb(integrand * self.E, dx=self.dlogE)[0] * log10
            else:
                ion = simps(integrand * self.E, x=self.logE) * log10    
                
        # Re-normalize
        ion *= 4. * np.pi * norm * fion_const
                
        # Currently a rate coefficient, returned value depends on return_rc
        if kw['return_rc']:
            pass
        else:
            ion *= self.coefficient_to_rate(z, species, **kw) 
        
        return ion
        
    def DiffuseLymanAlphaFlux(self, z, **kwargs):
        """
        Flux of Lyman-alpha photons induced by photo-electron collisions.
        
        """
            
        if not self.pf['secondary_lya']:
            return 0.0
        
        return 1e-25
        
        # Grab defaults, do some patches if need be    
        kw = self._fix_kwargs(**kwargs)
                
        # Compute fraction of photo-electron energy deposited as Lya excitation
        if self.esec.Method > 1 and (not self.pf['approx_xrb']) \
            and (kw['xray_flux'] is not None):
            if kw['igm_h_2'] == 0:
                flya = self.flya[:,0]
            else:
                if kw['igm_h_2'] > self.esec.x[self.i_x + 1]:
                    self.i_x += 1
                
                j = self.i_x + 1
                
                flya = self.flya[:,self.i_x] \
                    + (self.flya[:,j] - self.flya[:,self.i_x]) \
                    * (kw['igm_h_2'] - self.esec.x[self.i_x]) \
                    / (self.esec.x[j] - self.esec.x[self.i_x])                
        else:
            return 0.0
                
        # Re-normalize to help integrator
        norm = J21_num * self.sigma0
                
        # Compute integrand
        integrand = self.sigma_E[species] * (self.E - E_th[species])
       
        integrand *= kw['xray_flux'] * flya / norm / ev_per_hz
                         
        if kw['Emax'] is not None:
            imax = np.argmin(np.abs(self.E - kw['Emax']))
            if imax == 0:
                return 0.0
                
            if self.sampled_integrator == 'romb':
                raise ValueError("Romberg's method cannot be used for integrating subintervals.")
                heat = romb(integrand[0:imax] * self.E[0:imax], dx=self.dlogE[0:imax])[0] * log10
            else:
                heat = simps(integrand[0:imax] * self.E[0:imax], x=self.logE[0:imax]) * log10
        
        else:
            imin = np.argmin(np.abs(self.E - self.pop.pf['spectrum_Emin']))
            
            if self.sampled_integrator == 'romb':
                heat = romb(integrand[imin:] * self.E[imin:], 
                    dx=self.dlogE[imin:])[0] * log10
            elif self.sampled_integrator == 'trapz':
                heat = np.trapz(integrand[imin:] * self.E[imin:], 
                    x=self.logE[imin:]) * log10
            else:
                heat = simps(integrand[imin:] * self.E[imin:], 
                    x=self.logE[imin:]) * log10
          
        # Re-normalize, get rid of per steradian units
        heat *= 4. * np.pi * norm * erg_per_ev

        # Currently a rate coefficient, returned value depends on return_rc                                      
        if kw['return_rc']:
            pass
        else:
            heat *= self.coefficient_to_rate(z, species, **kw)

        return heat
        
    def OpticalDepth(self, z1, z2, E, **kwargs):
        """
        Compute the optical depth between two redshifts.
        
        If no keyword arguments are supplied, assumes the IGM is neutral.
        
        Parameters
        ----------
        z1 : float
            observer redshift
        z2 : float
            emission redshift
        E : float
            observed photon energy (eV)  
            
        Notes
        -----
        If keyword argument 'xavg' is supplied, it must be a function of 
        redshift.
        
        Returns
        -------
        Optical depth between z1 and z2 at observed energy E.
        
        """
        
        kw = self._fix_kwargs(functionify=True, **kwargs)
        
        # Compute normalization factor to help numerical integrator
        norm = self.cosm.hubble_0 / c / self.sigma0
        
        # Temporary function to compute emission energy of observed photon
        Erest = lambda z: self.RestFrameEnergy(z1, E, z)
            
        # Always have hydrogen
        sHI = lambda z: self.sigma(Erest(z), species=0)
                
        # Figure out number densities and cross sections of everything
        if self.approx_He:
            nHI = lambda z: self.cosm.nH(z) * (1. - kw['xavg'](z))
            nHeI = lambda z: nHI(z) * self.cosm.y
            sHeI = lambda z: self.sigma(Erest(z), species=1)
            nHeII = lambda z: 0.0
            sHeII = lambda z: 0.0
        elif self.self_consistent_He:
            if type(kw['xavg']) is not list:
                raise TypeError('hey! fix me')
                
            nHI = lambda z: self.cosm.nH(z) * (1. - kw['xavg'](z))
            nHeI = lambda z: self.cosm.nHe(z) \
                * (1. - kw['xavg'](z) - kw['xavg'](z))
            sHeI = lambda z: self.sigma(Erest(z), species=1)
            nHeII = lambda z: self.cosm.nHe(z) * kw['xavg'](z)
            sHeII = lambda z: self.sigma(Erest(z), species=2)
        else:
            nHI = lambda z: self.cosm.nH(z) * (1. - kw['xavg'](z))
            nHeI = sHeI = nHeII = sHeII = lambda z: 0.0
        
        tau_integrand = lambda z: norm * self.cosm.dldz(z) \
            * (nHI(z) * sHI(z) + nHeI(z) * sHeI(z) + nHeII(z) * sHeII(z))
            
        # Integrate using adaptive Gaussian quadrature
        tau = quad(tau_integrand, z1, z2, epsrel=self.rtol, 
            epsabs=self.atol, limit=self.divmax)[0] / norm
                                                    
        return tau
                            
    def TabulateOpticalDepth(self, xavg=lambda z: 0.0):
        """
        Compute optical depth as a function of (redshift, photon energy).
        
        Parameters
        ----------
        xavg : function
            Mean ionized fraction as a function of redshift.

        Notes
        -----
        Assumes logarithmic grid in variable x = 1 + z. Corresponding 
        grid in photon energy determined in _init_xrb.    
            
        Returns
        -------
        Optical depth table.
        
        """
        
        # Create array for each processor
        tau_proc = np.zeros([self.L, self.N])

        pb = ProgressBar(self.L * self.N, 'tau')
        pb.start()     

        # Loop over redshift, photon energy
        for l in range(self.L):

            for n in range(self.N):
                m = l * self.N + n + 1

                if m % size != rank:
                    continue

                # Compute optical depth
                if l == (self.L - 1):
                    tau_proc[l,n] = 0.0
                else:
                    tau_proc[l,n] = self.OpticalDepth(self.z[l], 
                        self.z[l+1], self.E[n], xavg=xavg)

                pb.update(m)
                    
        pb.finish()
        
        # Communicate results
        if size > 1:
            tau = np.zeros_like(tau_proc)       
            nothing = MPI.COMM_WORLD.Allreduce(tau_proc, tau)            
        else:
            tau = tau_proc
            
        return tau
        