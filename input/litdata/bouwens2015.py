"""
Bouwens et al., 2015, ApJ, 803, 34

Table 6. 4 the last 5 rows.
"""

info = \
{
 'reference': 'Bouwens et al., 2015, ApJ, 803, 34'
 'data': 'Table 5', 
 'fits': 'Table 6', 
}

redshifts = [3.8, 4.9, 5.9, 6.9, 7.9]

fits = {}

fits['lf'] = {}

fits['lf']['pars'] = \
{
 'Mstar': [-20.88, -21.17, -20.94, -20.87, -20.63], 
 'pstar': [1.97e-3, 0.74e-3, 0.5e-3, 0.29e-3, 0.21e-3],
 'alpha': [-1.64, -1.76, -1.87, -2.06, -2.02],
}

fits['lf']['err'] = \
{
 'Mstar': [0.08, 0.12, 0.2, 0.26, 0.36], 
 'pstar': [0.315e-3, 0.16e-3, 0.19e-3, 0.165e-3, 0.17e-3],  # should be asymmetric!
 'alpha': [0.04, 0.05, 0.1, 0.13, 0.23],
}

# Table 5
# Note: not currently including any of the upper limits
data = {}
data['lf'] = \
{
 3.8: {'M': [-22.69, -22.19, -21.69, -21.19, -20.69, -20.19, -19.69, -19.19,
             -18.69, -18.19, -17.69, -16.94, -15.94],
       'phi': [0.000003, 0.000015, 0.000134, 0.000393, 0.000678, 0.001696,
               0.002475, 0.002984, 0.005352, 0.006865, 0.010473, 0.024580,
               0.025080],
       'err': [0.000004, 0.000009, 0.000023, 0.000040, 0.000063, 0.000113,
               0.000185, 0.000255, 0.000446, 0.001043, 0.002229, 0.003500,
               0.007860],
      },
 4.9: {'M': [-23.11, -22.61, -22.11, -21.61, -21.11, -20.61, -20.11, -19.61, 
             -19.11, -18.36, -17.36, -16.36],
       'phi': [0.000002, 0.000006, 0.000034, 0.000101, 0.000265, 0.000676,
               0.001029, 0.001329, 0.002085, 0.004460, 0.008600, 0.024400],
       'err': [0.000002, 0.000003, 0.000008, 0.000014, 0.000025, 0.000046, 
               0.000067, 0.000094, 0.000171, 0.000540, 0.001760, 0.007160],
      },               
 5.9: {'M': [-22.52, -22.02, -21.52, -21.02, -20.52, -20.02, -19.52, -18.77, 
             -17.77, -16.77],
       'phi': [0.000002, 0.000015, 0.000053, 0.000176, 0.000320, 0.000698, 
               0.001246, 0.001290, 0.006680, 0.013640],
       'err': [0.000002, 0.000006, 0.000012, 0.000025, 0.000041, 0.000084, 
               0.000137, 0.000320, 0.001380, 0.004200],
      },
 6.9: {'M': [-22.16, -21.66, -21.16, -20.66, -20.16, -19.66, -19.16, -18.66,
             -17.91, -16.91],
       'phi': [0.000001, 0.000033, 0.000048, 0.000193, 0.000309, 0.000654,
               0.000907, 0.001717, 0.005840, 0.008500],
       'err': [0.000002, 0.000009, 0.000015, 0.000034, 0.000061, 0.000100, 
               0.000177, 0.000478, 0.001460, 0.002940],
      },
 7.9: {'M': [-21.87, -21.37, -20.87, -20.37, -19.87, -19.37, -18.62, -17.62],
       'phi': [0.000005, 0.000013, 0.000058, 0.000060,
               0.000331, 0.000533, 0.001060, 0.002740],
       'err': [0.000003, 0.000005, 0.000015, 0.000026,
               0.000104, 0.000226, 0.000340, 0.001040],
      }
}


