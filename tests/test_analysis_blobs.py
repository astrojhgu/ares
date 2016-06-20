"""

test_analysis_blobs.py

Author: Jordan Mirocha
Affiliation: UCLA
Created on: Thu May 26 11:28:43 PDT 2016

Description: 

"""

import os
import ares
import pickle
import numpy as np
import matplotlib.pyplot as pl

def test(Ns=500, Nd=4, prefix='test'):

    # Step 1. Make some fake data. 
    
    # Start with a 2-D array that looks like an MCMC chain with 500 samples in a 
    # 4-D parameter space. It's flat already (i.e., no walkers dimension)
    chain = np.reshape(np.random.normal(loc=0, scale=1., size=Ns*Nd), (Ns, Nd))
    
    # Random "likelihoods" -- just a 1-D array
    logL = np.random.rand(Ns)
    
    # Info about the parameters
    pars = ['par_%i' % i for i in range(Nd)]
    is_log = [False] * Nd
    pinfo = pars, is_log
    
    # Write to disk.
    with open('%s.chain.pkl' % prefix, 'wb') as f:
        pickle.dump(chain, f)
    with open('%s.pinfo.pkl' % prefix, 'wb') as f:
        pickle.dump(pinfo, f)    
    with open('%s.logL.pkl' % prefix, 'wb') as f:
        pickle.dump(logL, f)    
    
    # Make some blobs. 0-D, 1-D, and 2-D.
    setup = \
    {
     'blob_names': [['blob_0'], ['blob_1'], ['blob_2']], 
     'blob_ivars': [None, [np.arange(10)], [np.arange(10), np.arange(10,20)]],
    }
    
    with open('%s.setup.pkl' % prefix, 'wb') as f:
        pickle.dump(setup, f)
    
    # Blobs
    blobs = {}
    for i, blob_grp in enumerate(setup['blob_names']):
        
        if setup['blob_ivars'][i] is None:
            nd = 0
        else:
            nd = len(np.array(setup['blob_ivars'][i]).squeeze().shape)
    
        for blob in blob_grp:
            
            dims = [Ns]
            if nd > 0:
                dims.extend(map(len, setup['blob_ivars'][i]))
            
            data = np.reshape(np.random.normal(size=np.product(dims)), dims)
                    
            with open('%s.blob_%id.%s.pkl' % (prefix, nd, blob), 'wb') as f:
                pickle.dump(data, f)
            
    # Now, read stuff back in and make sure ExtractData works. Plotting routines?    
    anl = ares.analysis.ModelSet(prefix)    
    
    # Test a few things.
    
    # First, TrianglePlot, PosteriorPDFs
    mp = anl.TrianglePlot(anl.parameters, fig=1)
    ax1 = anl.PosteriorPDF(anl.parameters[0:2], fig=2)
    ax2 = anl.PosteriorPDF(anl.parameters[0], fig=3)
    
    # Test data extraction
    for par in anl.parameters:
        data, is_log = anl.ExtractData(par)
    
    # Second, finding error-bars.
    for par in anl.parameters:
        mu, bounds = anl.get_1d_error(par, nu=0.68)
    
    # Test blobs, including error-bars, extraction, and plotting.
    for par in anl.all_blob_names:
        mu, bounds = anl.get_1d_error(par, nu=0.68)
    
    for blob in anl.all_blob_names:
        data, is_log = anl.ExtractData(blob)
    
    # Plot test: first, determine ivars and then plot blobs against eachother.
    ivars = []
    for i, blob_grp in enumerate(setup['blob_ivars']):
        if setup['blob_ivars'][i] is None:
            nd = 0
        else:
            nd = len(np.array(setup['blob_ivars'][i]).squeeze().shape)
            
        if nd == 0:
            ivars.append(None)
        elif nd == 1:
            ivars.append(setup['blob_ivars'][i][0][0])
        else:
            ivars.append([setup['blob_ivars'][i][0][0], setup['blob_ivars'][i][1][0]])
        
    anl.TrianglePlot(anl.all_blob_names, ivar=ivars, fig=4)
    
    for i in range(1, 5):
        pl.figure(i)
        pl.savefig('%s_%i.png' % (__file__.rstrip('.py'), i))     
    
    pl.close('all')
    
    # Cleanup
    for suffix in ['chain', 'logL', 'pinfo', 'setup']:
        os.remove('%s.%s.pkl' % (prefix, suffix))
    
    for i, blob_grp in enumerate(setup['blob_names']):
    
        if setup['blob_ivars'][i] is None:
            nd = 0
        else:
            nd = len(np.array(setup['blob_ivars'][i]).squeeze().shape)
    
        for blob in blob_grp:
            os.remove('%s.blob_%id.%s.pkl' % (prefix, nd, blob))
    
    assert True

if __name__ == '__main__':
    test()
