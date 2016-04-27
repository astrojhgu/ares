"""

test_empirical.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Wed Sep  2 19:56:36 PDT 2015

Description: 

"""

import ares
import numpy as np
import matplotlib.pyplot as pl
from ares.physics.Constants import rhodot_cgs, cm_per_mpc

b15 = ares.util.read_lit('bouwens2015')

lf_pars = b15.fits['lf']['pars']
lf_pars['z'] = b15.redshifts

pars = \
{
 'pop_Tmin': 1e4,
 'pop_model': 'ham',
 'pop_Macc': 'mcbride2009',
 'pop_constraints': 'bouwens2015',
 'pop_lf_z': [3.8, 4.9, 5.9, 6.9, 7.9],
 #'pop_kappa_UV': 1.15e-28,
 'pop_sed': 'leitherer1999',
 
 'pop_ham_fit': 'fstar',
 'pop_ham_Mfun': 'lognormal',
 'pop_ham_zfun': 'const',
 'pop_ham_Mext': 'pl_floor',
 'pop_ham_Mext_par1': 3.0,
 'pop_ham_Mext_par2': 1./3.,
 #'pop_ham_zext': None,
 
 # Dust
 'pop_lf_dustcorr': True,
 'pop_lf_beta': -2.,
}

pop = ares.populations.GalaxyHAM(**pars)

fig0 = pl.figure(0); ax0 = fig0.add_subplot(111)
fig1 = pl.figure(1); ax1 = fig1.add_subplot(111)

# Plot fits compared to observational data
M = np.arange(-24, -10, 0.05)

colors = ['k', 'b', 'g', 'r', 'c', 'y', 'm']
for i, z in enumerate(pop.constraints['z']):
    ax0.scatter(b15.data['lf'][z]['M'], b15.data['lf'][z]['phi'],
        color=colors[i], edgecolors='none', s=50)
    phi = pop.LuminosityFunction(z, M, mags=True)
    ax0.semilogy(M + pop.A1600(z, M), phi, color=colors[i])
    
ax0.set_xlabel(r'$M_{\mathrm{UV}}$')
ax0.set_ylabel(r'$\phi(M)$')
ax0.set_ylim(1e-7, 1e-1)
ax0.set_xlim(-25, -15)

L = np.logspace(27., 31.)

# Plot Schecter function fits
for i, z in enumerate(pop.constraints['z']):
    phi = pop.constraints['pstar'][i] 
    phi *= (L / pop.constraints['Lstar'][i])**pop.constraints['alpha'][i]
    phi *= np.exp(-L / pop.constraints['Lstar'][i])
    phi /= pop.constraints['Lstar'][i]
    
    ax1.loglog(L, phi)
    
# Verify that we get out what we put in
for i, z in enumerate(pop.constraints['z']):
    phi = pop.LuminosityFunction(z, L, mags=False)
    ax1.loglog(L, phi, ls='--', lw=4)
   
ax1.set_xlabel(r'$L \ (\mathrm{erg} \ \mathrm{s}^{-1} \ \mathrm{Hz}^{-1})$')
ax1.set_ylabel(r'$\phi(L)$')
ax1.set_xlim(1e27, 1e31)
ax1.set_ylim(1e-39, 1e-29)
pl.show()



# SFE
fig2 = pl.figure(2); ax2 = fig2.add_subplot(111)

import time

colors = ['r', 'b', 'g', 'k', 'm']
for i, z in enumerate(pop.redshifts):
    j = pop.redshifts.index(z)
    ax2.scatter(pop.MofL_tab[j], pop.fstar_tab[j], 
        label=r'$z=%g$' % z, color=colors[i], marker='o', facecolors='none')
    
ax2.plot([1e8, 1e15], [0.2]*2, color='k', ls=':')
ax2.plot([1e8, 1e15], [0.3]*2, color='k', ls=':')
ax2.set_xlabel(r'$M_h / M_{\odot}$')
ax2.set_ylabel(r'$f_{\ast}$')
ax2.legend(ncol=1, frameon=False, fontsize=16, loc='lower right')

Marr = np.logspace(8, 14)
for i, z in enumerate(pop.redshifts):
    j = pop.redshifts.index(z)

    fast = pop.SFE(z=z, M=Marr)
    ax2.loglog(Marr, fast, color=colors[i])

colors2 = ['y', 'm', 'c', 'gray']*3
M2 = np.logspace(8, 14, 50)   
for i, z in enumerate([10, 15, 20, 25, 35, 45]):
    fast = pop.SFE(z=z, M=M2)
    ax2.loglog(M2, fast, color=colors2[i], ls='--')    
 
ax2.set_ylim(1e-3, 1.5)

import sys
sys.exit()


# SFR
fig3 = pl.figure(3); ax3 = fig3.add_subplot(111)
M6 = np.argmin(np.abs(pop.halos.M - 1e6))
for i, z in enumerate(pop.ham.redshifts):
    iz = np.argmin(np.abs(pop.halos.z - z))
    ax3.loglog(pop.halos.M[M6:], pop.ham.sfr_tab[iz,M6:])

ax3.set_xlabel(r'$M_h / M_{\odot}$')   
ax3.set_ylabel(r'$\dot{\rho}_{\ast} \ \left[M_{\odot} / \mathrm{yr} \right]$')

# SFRD
fig4 = pl.figure(4); ax4 = fig4.add_subplot(111)

zarr = np.arange(4, 40, 0.1)
sfrd_1 = np.array(map(pop.SFRD, zarr)) * rhodot_cgs
ax4.semilogy(zarr, sfrd_1, label='HAM')

# Compare to fcoll
pop_fcoll = ares.populations.GalaxyPopulation()

sfrd = np.array(map(pop_fcoll.SFRD, zarr)) * rhodot_cgs
pl.semilogy(zarr, sfrd, color='b', label='fcoll')

# Compare to R15
pop_r15 = ares.util.read_lit('robertson2015')
pl.semilogy(zarr, map(pop_r15.SFRD, zarr), color='g', label='R15')

ax4.set_xlabel(r'$z$')
ax4.set_ylabel(r'$\dot{\rho}_{\ast} \ \left[M_{\odot} / \mathrm{yr} / \mathrm{cMpc}^3 \right]$')
ax4.set_xlim(4, 30)
ax4.set_ylim(1e-5, 1)
pl.legend(loc='lower left', frameon=False)

# Halo mass - halo luminosity relationship
fig5 = pl.figure(5); ax5 = fig5.add_subplot(111)

# At z=6
for z in [6,7,8,9]:

    fast = pop.ham.SFE(z=z, M=pop.halos.M)
    iz = np.argmin(np.abs(z - pop.halos.z))
    ax5.loglog(pop.halos.M, pop.ham.sfr_tab[iz,:] / pop.pf['pop_kappa_UV'],
        label=r'$z=%i$' % z)

ax5.set_xlabel(r'$M_h / M_{\odot}$')  
ax5.set_ylabel(r'$L_h / (\mathrm{erg} \ \mathrm{s}^{-1} \ \mathrm{Hz}^{-1})$')  
ax5.set_xlim(1e8, 1e14)
ax5.set_ylim(1e25, 1e31)
ax5.legend(loc='upper left', frameon=False, fontsize=16)

# Ionization emissivity evolution
fig6 = pl.figure(6); ax6 = fig6.add_subplot(111)

Nion = 4000. * np.array(map(pop.SFRD, zarr)) * cm_per_mpc**3 / pop.cosm.g_per_baryon
ax6.semilogy(zarr, Nion, label='HAM')

ax6.set_ylabel(r'$N_{\mathrm{ion}} / (\mathrm{s}^{-1} \ \mathrm{cMpc}^{-3})$')
ax6.set_xlabel(r'$z$')

# Cumulative luminosity density
fig7 = pl.figure(7); ax7 = fig7.add_subplot(111)

from scipy.integrate import cumtrapz

for z in [6,7,8,9]:

    fast = pop.ham.SFE(z=z, M=pop.halos.M)
    iz = np.argmin(np.abs(z - pop.halos.z))
    to_int = pop.ham.sfr_tab[iz,:] * pop.halos.dndm[iz,:] / pop.pf['pop_kappa_UV']
    rhoL = cumtrapz(to_int, x=pop.halos.logM) \
        / np.trapz(to_int, x=pop.halos.logM)
    
    ax7.loglog(pop.halos.M[1:], rhoL, label=r'$z=%i$' % z)

ax7.set_xlabel(r'$M_h / M_{\odot}$')  
ax7.set_ylabel(r'$L_h / (\mathrm{erg} \ \mathrm{s}^{-1} \ \mathrm{Hz}^{-1})$')  
ax7.set_xlim(1e8, 1e13)
ax7.set_ylim(1e-2, 1.05)
ax7.set_title('cumulative luminosity')
ax7.legend(loc='upper left', frameon=False, fontsize=16)

pl.draw()

# SFE vs z
fig8 = pl.figure(8); ax8 = fig8.add_subplot(111)

z = np.linspace(5, 30)
for M in 10**np.arange(7, 14):
    fst = map(lambda z: pop.ham.SFE(z, M), z)
    pl.plot(z, fst, label=r'$M_h / M_{\odot} = 10^{%i}$' % (np.log10(M)))
    
ax8.set_xlabel(r'$z$')
ax8.set_ylabel(r'$f_{\ast}$')
ax8.set_yscale('log')
ax8.legend(loc='lower right', fontsize=14)

# eta vs z
fig9 = pl.figure(9); ax9 = fig9.add_subplot(111)

ax9.plot(pop.halos.z, pop.ham.eta / pop.cosm.fbaryon)
ax9.set_xlabel(r'$z$')
ax9.set_ylabel(r'$\eta(z)$')


