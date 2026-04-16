# Local Notes for `py_bonemat_abaqus`

This directory contains a vendored copy of `py_bonemat_abaqus`, used by the BoneMat Slicer extension.

## Origin

- Upstream project: https://github.com/modenaxe/py_bonemat_abaqus
- Original author: Dr Elise Pegg, Dr Luca Modenese
- License: GPLv3
- Imported as: git subtree

## Local Purpose

BoneMat imports some data importing functions, important classes, and the main functions related to the material mapping:

```python
from py_bonemat_abaqus.data_import import _checkParamInformation, _create_part
from py_bonemat_abaqus.classes import part, vtk_data
from py_bonemat_abaqus.calc import _check_elements_in_CT, _assign_mat_props, _limit_num_materials
```

## Local Changes

### Removed files

The following files/directories were removed because they are unused by my extension, or unnecessary boilerplate:
* `.gitignore`
* `MANIFEST.in`
* `setup.py`
* `setup.cfg`
* `py_bonemat_abaqus.py`
* `py_bonemat_abaqus/tests/`
* `py_bonemat_abaqus/example/`
* `py_bonemat_abaqus/command_line.py`
* `py_bonemat_abaqus/data_output.py`
* `py_bonemat_abaqus/general.py`
* `py_bonemat_abaqus/run.py`
* `py_bonemat_abaqus/version.py`

### Changed files

The following files were changed substantially:
* `py_bonemat_abaqus/data_import.py`
  * All functions except for `_checkParamInformation`, `_create_part` and the functions they each call, were removed.
  * No changes were made to the kept functions
* `py_bonemat_abaqus/calc.py`
  * The functions `calc_mat_props`, `_identify_voxels_in_tets`, `_refine_materials`, `_get_all_modulus_values` and `_get_mod_intervals` were removed because they were refactored out or bypassed completely.
  * Changes were made to several of the remaining functions, including:
    * `_assign_mat_props(part, param, vtk, progressBar)`
      * **Changes**: Added the `progressBar` parameter. Changed all the list comprehensions into enumerated for-loops. Added checks within each loop for when the `progressBar` should be incremented.
      * **Reason**: The `progressBar` needs to be updated wherever the main assignment loop is happening, hence the additional parameter. Accurate incrementing of the `progressBar` requires knowing how many of the elements have been assigned a modulus, which means knowing the index of the current loops.
    * `_check_elements_in_CT(part, vtk)`
      * **Changes**: Got rid of the loop which looked through a list of parts, it instead checks the validity of the single part given.
      * **Reason**: My extension only passes through a mesh definition with one part, not many.
    * `_limit_num_materials(moduli, gapValue, minVal, groupingDensity)`
      * **Changes**: Changed the main binning loop to use a decreasing `end` variable to mark the end of the current array, rather than overwriting the array variable. Removed the warning about number of bins and computation time which prompted the user for input. Added a case when the `gapValue == 1` which rounds the data up rather dealing with many small bins.
      * **Reason**: Performance improvements. Removed the potential for stalling while waiting for user input in the Slicer python console.
* `py_bonemat_abaqus/__init__.py`
  * The modules which were deleted were removed from the `__all__` list.

### Unchanged files

The following files were kept and no significant changes were made:
* `py_bonemat_abaqus/classes.py`
