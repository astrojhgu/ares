"""

FitGLF.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Fri Oct 23 14:34:01 PDT 2015

Description: 

"""

import numpy as np
from ..util import read_lit
from .ModelFit import LogLikelihood
from ..util.PrintInfo import print_fit
from .FitGlobal21cm import FitGlobal21cm
import gc, os, sys, copy, types, time, re
from ..util.ParameterFile import par_info
from ..simulations import Global21cm as simG21
from ..simulations import MultiPhaseMedium as simMPM
from ..analysis.InlineAnalysis import InlineAnalysis
from ..util.SetDefaultParameterValues import _blob_names, _blob_redshifts, \
    SetAllDefaults

try:
    import dill as pickle
except:
    import pickle

try:
    from emcee.utils import sample_ball
except ImportError:
    pass

try:
    from mpi4py import MPI
    rank = MPI.COMM_WORLD.rank
    size = MPI.COMM_WORLD.size
except ImportError:
    rank = 0
    size = 1
    
twopi = 2. * np.pi

defaults = SetAllDefaults()

def _which_sim_inst(**kw):
    if 'include_igm' in kw:
        if kw['include_igm']:
            _sim_class = simG21
        else:
            _sim_class = simMPM
    elif defaults['include_igm']:
        _sim_class = simG21
    else:
        _sim_class = simMPM
    
    return _sim_class

class loglikelihood(LogLikelihood):

    @property
    def runsim(self):
        if not hasattr(self, '_runsim'):
            self._runsim = True
        return self._runsim
    @runsim.setter
    def runsim(self, value):
        self._runsim = value

    @property
    def redshifts(self):
        return self._redshifts
    @redshifts.setter
    def redshifts(self, value):
        self._redshifts = value

    @property
    def sim_class(self):
        if not hasattr(self, '_sim_class'):
            self._sim_class = _which_sim_inst(**self.base_kwargs)        
                
        return self._sim_class
        
    @property
    def const_term(self):
        if not hasattr(self, '_const_term'):
            self._const_term = -np.log(np.sqrt(twopi)) \
                             -  np.sum(np.log(self.error))
        return self._const_term                     

    def __call__(self, pars, blobs=None):
        """
        Compute log-likelihood for model generated via input parameters.
    
        Returns
        -------
        Tuple: (log likelihood, blobs)
    
        """
                
        kwargs = {}
        for i, par in enumerate(self.parameters):
        
            if self.is_log[i]:
                kwargs[par] = 10**pars[i]
            else:
                kwargs[par] = pars[i]

        # Apply prior on model parameters first (dont need to generate signal)
        point = {}
        for i in range(len(self.parameters)):
            point[self.parameters[i]] = pars[i]
        
        lp = self.priors_P.log_prior(point)
        if not np.isfinite(lp):
            return -np.inf, self.blank_blob

        # Run a model and retrieve turning points
        kw = self.base_kwargs.copy()
        kw.update(kwargs)
        
        # Don't save base_kwargs for each proc! Needlessly expensive I/O-wise.
        self.checkpoint(**kwargs)

        sim = self.sim = self.sim_class(**kw)

        if isinstance(sim, simG21):
            medium = sim.medium
        else:
            medium = sim

        # If we're only fitting the LF, no need to run simulation
        if self.runsim:

            try:
                sim.run()                
            except (ValueError, IndexError):
                # Seems to happen if Tmin goes crazy big 
                # (IndexError in integration)
                
                f = open('%s.fail.%s.pkl' % (self.prefix, str(rank).zfill(3)), 
                    'ab')
                pickle.dump(kwargs, f)
                f.close()
                
                del sim, kw, f
                gc.collect()
                
                return -np.inf, self.blank_blob
        
        if self.priors_B.params != []:
            lp += self._compute_blob_prior(sim)

        # emcee will crash if this returns NaN. OK if it's inf though.
        if np.isnan(lp):
            return -np.inf, self.blank_blob

        # Figre out which population is the one with the LF
        for popid, pop in enumerate(medium.field.pops):
            if pop.is_fcoll_model:
                continue

            break

        # Compute the luminosity function, goodness of fit, return
        phi = []
        for i, z in enumerate(self.redshifts):
            xdat = np.array(self.xdata[i])

            # Apply dust correction to observed data, which is uncorrected
            M = xdat - pop.AUV(z, xdat) 
            
            # Generate model LF
            p = pop.LuminosityFunction(z=z, x=M, mags=True)
            phi.extend(p)           
                
        lnL = 0.5 * np.sum((np.array(phi) - self.ydata)**2 / self.error**2)    
        PofD = self.const_term - lnL
                    
        if np.isnan(PofD):
            return -np.inf, self.blank_blob

        try:
            blobs = sim.blobs
        except:
            blobs = self.blank_blob    

        del sim, kw
        gc.collect()

        return lp + PofD, blobs
    
class FitLuminosityFunction(FitGlobal21cm):
    """
    Basically a Global21cm fit except we might not actually press "run" on
    any of the simulations. By default, we don't.
    """
    
    def __init__(self, **kwargs):
        FitGlobal21cm.turning_points = False
        FitGlobal21cm.__init__(self, **kwargs)
            
    @property
    def runsim(self):
        if not hasattr(self, '_runsim'):
            self._runsim = False
        return self._runsim
    
    @runsim.setter
    def runsim(self, value):
        self._runsim = value
        
    @property 
    def save_hmf(self):
        if not hasattr(self, '_save_hmf'):
            self._save_hmf = True
        return self._save_hmf
    
    @save_hmf.setter
    def save_hmf(self, value):
        self._save_hmf = value
    
    @property 
    def save_psm(self):
        if not hasattr(self, '_save_psm'):
            self._save_psm = True
        return self._save_psm
    
    @save_psm.setter
    def save_psm(self, value):
        self._save_psm = value    
    
    @property
    def loglikelihood(self):
        if not hasattr(self, '_loglikelihood'):

            if (self.save_hmf or self.save_psm):
                sim_class = _which_sim_inst(**self.base_kwargs)
                
                sim = sim_class(**self.base_kwargs)
                
                if isinstance(sim, simG21):
                    medium = sim.medium
                else:
                    medium = sim
                    
                for popid, pop in enumerate(medium.field.pops):
                    if pop.is_fcoll_model:
                        continue
                
                    break
                
                self.pops = medium.field.pops
                    
                if self.save_hmf:
                    hmf = pop.halos
                    assert 'hmf_instance' not in self.base_kwargs
                    self.base_kwargs['hmf_instance'] = hmf    
                if self.save_psm:
                    #raise NotImplemented('help')
                    psm = pop.src
                    assert 'pop_psm_instance' not in self.base_kwargs
                    self.base_kwargs['pop_psm_instance{%i}' % popid] = psm

            self._loglikelihood = loglikelihood(self.xdata, 
                self.ydata_flat, self.error_flat, 
                self.parameters, self.is_log, self.base_kwargs, 
                self.prior_set_P, self.prior_set_B, 
                self.prefix, self.blob_info, self.checkpoint_by_proc)   
            
            self._loglikelihood.runsim = self.runsim
            self._loglikelihood.redshifts = self.redshifts

            self.info

        return self._loglikelihood

    @property
    def redshifts(self):
        if not hasattr(self, '_redshifts'):
            raise ValueError('Set by hand or include in litdata.')
            
        return self._redshifts
                    
    @redshifts.setter
    def redshifts(self, value):
        # This can be used to override the redshifts in the dataset and only
        # use some subset of them
        if not hasattr(self, '_redshifts'):
            raise NotImplemented('you should have already set the redshifts')
            
        if type(value) in [int, float]:
            value = [value]
            
        tmp1 = copy.deepcopy(self._redshifts)
        tmp2 = []
        for redshift in value:
            if redshift not in tmp1:
                raise ValueError('Redshift %g not in this dataset!')        
            tmp2.append(redshift)

        self._redshifts = tmp2    

    @property
    def data(self):
        if not hasattr(self, '_data'):
            raise AttributeError('Must set data by hand!')
        return self._data    
                
    @data.setter
    def data(self, value):
        if type(value) == str:
            litdata = read_lit(value)
            self._data = litdata.data['lf']
            self._redshifts = litdata.redshifts
        else:
            raise NotImplemented('help!')
                                        
    @property
    def xdata_flat(self):
        if not hasattr(self, '_xdata_flat'):
            self._mask = []
            self._xdata_flat = []; self._ydata_flat = []
            self._error_flat = []; self._redshifts_flat = []
            for i, redshift in enumerate(self.redshifts):
                self._mask.extend(self.data[redshift]['M'].mask)
                self._xdata_flat.extend(self.data[redshift]['M'])
                self._ydata_flat.extend(self.data[redshift]['phi'])
                
                # Cludge for asymmetric errors
                for j, err in enumerate(self.data[redshift]['err']):
                    if type(err) in [tuple, list]:
                        self._error_flat.append(np.mean(err))
                    else:
                        self._error_flat.append(err)
                
                zlist = [redshift] * len(self.data[redshift]['M'])
                self._redshifts_flat.extend(zlist)
                
            self._xdata_flat = np.ma.array(self._xdata_flat, mask=self._mask)
            self._ydata_flat = np.ma.array(self._ydata_flat, mask=self._mask)
            self._error_flat = np.ma.array(self._error_flat, mask=self._mask)

        return self._xdata_flat
    
    @property
    def ydata_flat(self):
        if not hasattr(self, '_ydata_flat'):
            xdata_flat = self.xdata_flat
    
        return self._ydata_flat      
    
    @property
    def error_flat(self):
        if not hasattr(self, '_error_flat'):
            xdata_flat = self.xdata_flat
    
        return self._error_flat   
    
    @property
    def redshifts_flat(self):
        if not hasattr(self, '_redshifts_flat'):
            xdata_flat = self.xdata_flat
    
        return self._redshifts_flat      
    
    @property
    def xdata(self):
        if not hasattr(self, '_xdata'):
            if hasattr(self, '_data'):
                self._xdata = []; self._ydata = []; self._error = []
                for i, redshift in enumerate(self.redshifts):
                    self._xdata.append(self.data[redshift]['M'])
                    self._ydata.append(self.data[redshift]['phi'])
                    self._error.append(self.data[redshift]['err'])
                    
        return self._xdata
        
    @xdata.setter
    def xdata(self, value):
        self._xdata = value
        
    @property
    def ydata(self):
        if not hasattr(self, '_ydata'):
            if hasattr(self, '_data'):
                xdata = self.xdata
                
        return self._ydata    
    
    @ydata.setter
    def ydata(self, value):
        self._ydata = value
        
    @property
    def error(self):
        if not hasattr(self, '_error'):
            if hasattr(self, '_data'):
                xdata = self.xdata
        return self._error
    
    @error.setter
    def error(self, value):
        self._error = value    
    
    @property
    def guess_override(self):
        if not hasattr(self, '_guess_override_'):
            self._guess_override_ = {}
        
        return self._guess_override_
    
    @guess_override.setter
    def guess_override(self, kwargs):
        if not hasattr(self, '_guess_override_'):
            self._guess_override_ = {}
            
        self._guess_override_.update(kwargs)
                        
    def save_data(self, prefix, clobber=False):
        if rank > 0:
            return
            
        fn = '%s.data.pkl' % prefix
        
        if os.path.exists(fn) and (not clobber):
            print "%s exists! Set clobber=True to overwrite." % fn
            return
                
        f = open(fn, 'wb')
        pickle.dump((self.xdata, self.ydata, self.redshifts, self.error), f)
        f.close()
     
    
