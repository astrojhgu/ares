# -*- coding: utf-8 -*-
import numpy as np

"""
YOSHIHIRO UEDA, MASAYUKI AKIYAMA, GÜNTHER HASINGER, TAKAMITSU MIYAJI,
MICHAEL G. WATSON, 2015, ???, ???, ???

This model is the more complicated version of Ueda et al. (2003) double power law
  
  
NOTE: 
    
    --- = spacing between different sections of code
    
    ### = spacing within a section of code to denote a different section within that particular code

"""

#-------------------------------------------------


qsolf_LDDE2_hardpars = \
{
 'A': 10**-6 *.70**3 * 2.91,
 'loglstar': 10**43.97,
 'gamma1': 0.96,
 'gamma2': 2.71,
 'p1': 4.78,
 'p2': -1.5,
 'p3': -6.2,
 'beta1': 0.84,
 'zstar': 1.86,
 'zstarc2': 3.0,
 'logLa': 10**44.61,
 'logLa2': 10**45.67,#???
 'alpha': 0.29,
 'alpha2': -0.1
}

qsolf_LDDE2_harderr = \
{
 'A_err': 0.07, 
 'loglstar_err': 10**0.06,
 'gamma1_err': 0.04,
 'gamma2_err': 0.09,
 'p1_err': 0.16,
 'p2_err': 0,
 'p3_err': 0,
 'beta1_err': 0.18,
 'zstar_err': 0.07,
 'zstarc2_err': 0,
 'logLa_err': 10**0.07,
 'logLa2_err': 0,
 'alpha_err': 0.02,
 'alpha2_err': 0
}

#-------------------------------------------------  

def randomsamples(samples, K = None, loglstar = None, \
gamma1 = None, gamma2 = None, p1 = None, p2  = None,\
p3  = None, beta1 = None, zstar = None, zstarc2  = None, 
logLa = None, logLa2 = None, alpha = None, alpha2 = None,\
K_err = None, loglstar_err = None, gamma1_err = None, 
gamma2_err = None, p1_err = None, p2_err = None, p3_err = None, \
beta1_err = None, zstar_err = None, zstarc2_err = None,\
logLa_err = None, logLa2_err = None, alpha_err = None, \
alpha2_err = None, **kwargs):

    randomsamples = []
    for i in range(samples):
        
        randomsample = {
        #'K': np.random.normal(K, K_err, samples),
        'A': 10**-6 *.70**3 * 2.91,
        'loglstar': np.random.normal(loglstar, loglstar_err, samples)[i],\
        'gamma1': np.random.normal(gamma1, gamma1_err, samples)[i],\
        'gamma2': np.random.normal(gamma2, gamma2_err, samples)[i],\
        'p1': np.random.normal(p1, p1_err, samples)[i],\
        'p2': -1.5,\
        'p3': -6.2,\
        'beta1': np.random.normal(beta1, beta1_err, samples)[i],\
        'zstar': np.random.normal(zstar, zstar_err, samples)[i],\
        'zstarc2': 3.0,\
        'logLa': np.random.normal(logLa, logLa_err, samples)[i],\
        'logLa2': 10**45.67,\
        'alpha': np.random.normal(alpha, alpha_err, samples)[i],\
        'alpha2': -0.1\
        }
        randomsamples.append(randomsample)
    return randomsamples
   

#-------------------------------------------------

def _LuminosityFunction_LDDE(Lx, z, loglstar = None, A = None, gamma1 = None, gamma2 = None, p1 = None, p2  = None,\
p3  = None, beta1 = None, zstar = None, zstarc2  = None, logLa = None, logLa2 = None, alpha = None, alpha2 = None, **kwargs):

    
    if Lx <= logLa:
        zc1 = zstar*(Lx / logLa)**alpha
    elif Lx > logLa:
        zc1 = zstar
    
    if Lx <= logLa2:
        zc2 = zstarc2*(Lx / logLa2)**alpha2
    elif Lx > logLa2:
        zc2 = zstarc2
##################################################       
    if z <= zc1:
        ex = (1+z)**p1
    elif zc1 < z <= zc2:
        ex = (1+zc1)**p1*((1+z)/(1+zc1))**p2
    elif z > zc2:
        ex = (1+zc1)**p1*((1+zc2)/(1+zc1))**p2*((1+z)/(1+zc2))**p3
   
    return  A * ((Lx / loglstar)**gamma1 + (Lx / loglstar)**gamma2)**-1 * ex