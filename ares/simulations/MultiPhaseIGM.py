"""

MultiPhaseIGM.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Mon Feb 16 12:46:28 MST 2015

Description: 

"""

import numpy as np
from .GasParcel import GasParcel
from ..util.ReadData import _sort_data
from ..solvers import UniformBackground
from ..util import ParameterFile, ProgressBar
from ..populations import CompositePopulation

igm_pars = \
{
 'grid_cells': 1,
 'isothermal': False,
 'expansion': True,
 'initial_ionization': [1.-1.2e-3, 1.2e-3],
 'cosmological_ics': True,
}

cgm_pars = \
{
 'grid_cells': 1,
 'isothermal': True,
 'initial_ionization': [1. - 1e-8, 1e-8, ],
 'initial_temperature': [1e4],
 'expansion': True,
 'cosmological_ics': True,
}

class MultiPhaseIGM:
    def __init__(self, **kwargs):
        self.pf = ParameterFile(**kwargs)

        # Initialize two GasParcels
        self.kw_igm = self.pf.copy()
        self.kw_igm.update(igm_pars)

        self.kw_cgm = self.pf.copy()
        self.kw_cgm.update(cgm_pars)

        self.parcel_igm = GasParcel(**self.kw_igm)
        self.parcel_cgm = GasParcel(**self.kw_cgm)

        # Fix CGM parcel to have negligible volume filling factor
        self.parcel_cgm.grid.data['Tk'] = np.array([1e4])
        self.parcel_cgm.grid.set_recombination_rate(in_bubbles=True)

        # Initialize generators
        self.gen_igm = self.parcel_igm.step()
        self.gen_cgm = self.parcel_cgm.step()
    
        self._set_radiation_field()
    
    def _set_radiation_field(self):
        """
        Loop over populations, make separate RB and RS instances for each.
        """

        self.field = UniformBackground(grid=self.parcel_igm.grid, **self.pf)

    def run(self):
        """
        Run simulation from start to finish.

        Returns
        -------
        Nothing: sets `history` attribute.

        """
                
        z = self.pf['initial_redshift']
        zf = self.pf['final_redshift']
        tf = self.parcel_igm.grid.cosm.LookbackTime(zf, z)
                
        pb = ProgressBar(tf, use=self.pf['progress_bar'])
        pb.start()
        
        # Rate coefficients for initial conditions
        self.parcel_igm.update_rate_coefficients(self.parcel_igm.grid.data, 
            **self.field.volume.rates_no_RT)
            
        all_t = []; all_z = []
        all_data_igm = []; all_data_cgm = []
        for t, z, data_igm, data_cgm in self.step():
            
            try:
                pb.update(t)
            except AssertionError:
                pass

            # Save data
            all_z.append(z)
            all_t.append(t)
            all_data_igm.append(data_igm.copy())  
            all_data_cgm.append(data_cgm.copy())
                        
        pb.finish()          

        self.history_igm = _sort_data(all_data_igm, prefix='igm_')
        self.history_cgm = _sort_data(all_data_cgm, prefix='cgm_')
        
        self.history = self.history_igm.copy()
        self.history.update(self.history_cgm)
        self.history['t'] = np.array(all_t)
        self.history['z'] = np.array(all_z)    
        
    def step(self):
        """
        Generator for a two-phase intergalactic medium.
        
        Returns
        -------
        Tuple containing the current time, redshift, and dictionaries for the
        IGM and CGM data at a single snapshot.
        
        """

        t = 0.0
        z = self.pf['initial_redshift']
        dt = self.pf['time_units'] * self.pf['initial_timestep']
        zf = self.pf['final_redshift']
        
        # Read initial conditions
        data_igm = self.parcel_igm.grid.data.copy()
        data_cgm = self.parcel_cgm.grid.data.copy()
                
        # Evolve in time!        
        while z > zf:

            # Increment time / redshift
            dtdz = self.parcel_igm.grid.cosm.dtdz(z)
            t += dt
            z -= dt / dtdz
            
            # IGM rate coefficients
            RC_igm = self.field.update_rate_coefficients(data_igm, z, 
                zone='igm', return_rc=True)
            
            # Now, update IGM parcel
            t1, dt1, data_igm = self.gen_igm.next()

            # Re-compute rate coefficients
            self.parcel_igm.update_rate_coefficients(data_igm, **RC_igm)

            # CGM rate coefficients
            RC_cgm = self.field.update_rate_coefficients(data_cgm, z, 
                zone='cgm', return_rc=True)

            # Re-compute rate coefficients
            self.parcel_cgm.update_rate_coefficients(data_cgm, **RC_cgm)

            # Now, update CGM parcel
            t2, dt2, data_cgm = self.gen_cgm.next()
            
            # Must update timesteps in unison
            dt = min(dt1, dt2)
            self.parcel_igm.dt = dt
            self.parcel_cgm.dt = dt
            
            yield t, z, data_igm, data_cgm

            