# Local Notes for py_bonemat_abaqus

This directory contains a vendored copy of `py_bonemat_abaqus`, used by the BoneMat Slicer extension.

## Origin

- Upstream project: https://github.com/modenaxe/py_bonemat_abaqus
- Original author: Dr Elise Pegg, Dr Luca Modenese
- License: GPLv3
- Imported as: git subtree

## Local Purpose

BoneMat imports the main mapping function as well as some helper functions and classes:

```python
from py_bonemat_abaqus.data_import import _checkParamInformation, _create_part
from py_bonemat_abaqus.classes import part, vtk_data
from py_bonemat_abaqus.calc import calc_mat_props
```

## Local Changes

* `py_bonemat_abaqus/calc.py`
  * `calc_mat_props(part, param, vtk)`
    * **Changes**: Changed the `parts` parameter name to `part`, removed loop which assigned moduli to a list of parts with a single call for a single part.
    * **Reason**: Whilst `py_bonemat_abaqus` was designed to deal with larger ABAQUS files which contain many distinct parts, my extension treats the input mesh from Slicer as one large part, and so there's no need for the list or loop.
  * `_check_elements_in_CT(part, vtk)`
    * **Changes**: Got rid of the loop which looked through a list of parts, it instead checks the validity of the single part given.
    * **Reason**: My extension only passes through a mesh definition with one part, not many.
  * `_check_fle_exists(fle)`
    * **Changes**: Instead of looking for files in the current directory, it checks if the given path exists
    * **Reason**: I'm writing files to a temporary directory instead of this one because I can't add files to the filesystem of a user.
  * `_limit_num_materials(moduli, gapValue, minVal, groupingDensity)`
    * **Changes**: Changed the main binning loop to use a decreasing `end` variable to mark the end of the current array, rather than overwriting the array variable. Removed the warning about number of bins and computation time which prompted the user for input. Added a case when the `gapValue == 1` which rounds the data up rather dealing with many small bins.
    * **Reason**: Performance improvements and potential for crashing.

* `py_bonemat_abaqus/run.py`
  * `run(argv0, argv1, argv2)`
    * **Changes**: Ends with `return` instead of `sys.exit(0)`
    * **Reason**: `sys.exit(0)` exits the entire Slicer program instead of just the function when imported. Very necessary change.

