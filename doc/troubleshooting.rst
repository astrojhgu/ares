Troubleshooting
===============
This page is an attempt to keep track of common errors and instructions for how to fix them. 

``IOError: No such file or directory``
--------------------------------------
There are a few different places in the code that will attempt to read-in lookup tables of various sorts. If you get any error that suggests a required input file has not been found, you should:

- Make sure you have set the ``$ARES`` environment variable. See the :doc:`install` page for instructions.
- Make sure the required file is where it should be, i.e., nested under ``$ARES/input``.

In the event that a required file is missing, something has gone wrong. Many lookup tables are downloaded automatically when you run the ``setup.py`` script, so the first thing you should do is re-run ``python setup.py install``. 

``LinAlgError: singular matrix``
--------------------------------
This is an odd one, known to occur in ``ares.physics.Hydrogen`` when using ``scipy.interpolate.interp1d`` to compute the collisional coupling coefficients for spin-exchange. 

We still aren't sure why this happens -- it cannot always be reproduced, even by two users using the same version of *scipy*. A temporary hack is to use linear interpolation, instead of a spline, or to hack off data points at high temperatures in the lookup table. Working on a more satisfying solution...email me if you encounter this problem.


