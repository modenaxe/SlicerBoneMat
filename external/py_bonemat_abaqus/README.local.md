# Local Notes for py_bonemat_abaqus

This directory contains a vendored copy of `py_bonemat_abaqus`, used by the BoneMat Slicer extension.

## Origin

- Upstream project: https://github.com/modenaxe/py_bonemat_abaqus
- Original author: Dr Elise Pegg, Dr Luca Modenese
- License: GPLv3
- Imported as: git subtree

## Local Purpose

BoneMat imports the main mapping function:

```python
from py_bonemat_abaqus.run import run
```

## Local Changes

* `py_bonemat_abaqus/calc.py`
  * `_check_fle_exists(fle)`
    * **Change**: instead of looking for files in the current directory, it checks if the given path exists
    * **Reason**: I'm writing files to a temporary directory instead of this one because I can't add files to the filesystem of a user.

* `py_bonemat_abaqus/run.py`
  * `run(argv0, argv1, argv2)`
    * **Change**: ends with `return` instead of `sys.exit(0)`
    * **Reason**: `sys.exit(0)` exits the entire Slicer program instead of just the function when imported. Very necessary change

