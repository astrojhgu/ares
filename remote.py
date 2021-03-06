#!/usr/bin/env python

import os, re, urllib, sys, tarfile

options = sys.argv[1:]

ares_link = 'https://bitbucket.org/mirochaj/ares'
         
# Auxiliary data downloads
# Format: [URL, file 1, file 2, ..., file to run when done]

#_bpassv2_links = \
#[
# ''
#]
#
aux_data = \
{
 'hmf': ['%s/downloads' % ares_link, 
    'hmf_ST_logM_1200_4-16_z_1141_3-60.npz',
    None],
 'inits': ['%s/downloads' % ares_link, 
     'initial_conditions.npz',
     None],    
 'optical_depth': ['%s/downloads' % ares_link,
    'optical_depth_H_400x1616_z_10-50_logE_2-4.7.npz',
    'optical_depth_He_400x1616_z_10-50_logE_2-4.7.npz',
    None],
 'secondary_electrons': ['%s/downloads' % ares_link,
    'elec_interp.tar.gz', 
    'read_FJS10.py'],
 'starburst99': ['http://www.stsci.edu/science/starburst99/data',
    'data.tar.gz', 
    None],                        
 #'hm12': ['http://www.ucolick.org/~pmadau/CUBA/Media',
 #   'UVB.out', 
 #   'emissivity.out', 
 #   None],
 'bpass_v1': ['http://bpass.auckland.ac.nz/2/files'] + \
    ['sed_bpass_z%s_tar.gz' % Z for Z in ['001', '004', '008', '020', '040']] + \
    [None],
 #'bpass_v2': ['https://drive.google.com/file/d/'] + \
 #    ['bpassv2-imf%i-300tar.gz' % IMF for IMF in [100, 135]] + \
 #     [None],    
}

if not os.path.exists('input'):
    os.mkdir('input')

os.chdir('input')

files = []
if (len(options) > 0) and ('clean' not in options):
    if 'minimal' in options:
        to_download = ['inits', 'secondary_electrons']
        files = [None, None]
    elif 'clean' in options:
        to_download = aux_data.keys()
        files = [None] * len(to_download)
    else:
        to_download = []
        for key in options:
            if key == 'fresh':
                continue
                
            if re.search(':', key):
                pre, post = key.split(':')
                to_download.append(pre)
                files.append(int(post))
            else:
                to_download.append(key)
                files.append(None)
                
        if to_download == [] and 'fresh' in options:
            to_download = aux_data.keys()
            files = [None] * len(to_download)        
else:
    to_download = aux_data.keys()
    files = [None] * len(to_download)
        
for i, direc in enumerate(to_download):
                
    if not os.path.exists(direc):
        os.mkdir(direc)
    
    os.chdir(direc)
    
    web = aux_data[direc][0]
    
    if files[i] is None:
        fns = aux_data[direc][1:-1]
    else:
        fns = [aux_data[direc][1:-1][files[i]]]
        
    for fn in fns:
            
        if os.path.exists(fn):
            if ('fresh' in options) or ('clean' in options):
                os.remove(fn)
            else:
                continue
            
        # 'clean' just deletes files, doesn't download new ones
        if 'clean' in options:
            continue
    
        print "Downloading %s/%s..." % (web, fn)
        
        try:
            urllib.urlretrieve('%s/%s' % (web, fn), fn)
        except:
            print "WARNING: Error downloading %s/%s" % (web, fn)
            continue
        
        # If it's not a tarball, move on
        if not re.search('tar', fn):
            continue
            
        # Otherwise, unpack it
        try:
            tar = tarfile.open(fn)
            tar.extractall()
            tar.close()
        except:
            print "WARNING: Error unpacking %s/%s" % (web, fn)
    
    # Run a script [optional]
    if aux_data[direc][-1] is not None:
        try:
            execfile(aux_data[direc][-1])
        except:
            print "WARNING: Error running %s" % aux_data[direc][-1] 
    
    os.chdir('..')


