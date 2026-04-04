# SlicerBoneMat

This is a 3D Slicer extension for assigning material properties (specifically Young's Modulus) to volumetric meshes using CT voxel intensities.

It's designed to be a modern, open-source equivalent of the original BoneMat software, with some much-needed improvements to the UI, supported I/O formats and phantom calibration abilities.

![Alt text](Screenshot01.png?raw=true "Segment Mesher module user interface")

## Usage

Here is a brief description of how to use the various sections of the module's UI:
* Input/output models
  * Select the input CT volume (likely a DICOM series)
  * Select the input volumetric mesh (can be created from a surface model using the SegmentMesher extension)
  * Select the output model
* Input mesh summary
  * Press the 'Calculate' button to summarise the input volumetric mesh
  * It calculates statistics such as:
    * Number of nodes
    * Number of elements
    * Element volumes
    * Maximum element edge length
    * Minimum element edge length
  * A grouped distribution of some of these statistics also appears
* Advanced
  * This section includes the phantom calibration capability and the HU to Young's Modulus formulas
  * If you want to use phantom calibration, click the checkbox and enter the 4 values in the table as example conversions
    * Since phantom calibration derives the HU to CT density formula, enabling it disables the related input fields
  * After entering the values for the evaluation steps, you can create a new preset to save them for later
* Options
  * The options here allow for further finetuning
  * Some further clarification:
    * The 3 algorithm choices reflect the 3 published versions of BoneMat over the years
    * Poisson's ratio is used in the output formats, as it is important for the FEA solvers to perform simulations
    * The gap value is the gap between the bins that the Young's modulus values are grouped into
* Download options
  * The extension currently supports 4 output formats, including:
    * VTK
    * ABAQUS
    * ANSYS
    * FEBio

## License

This project is released under the GNU General Public License v3 (GPLv3). While Slicer typically prefers more permissive licenses, this module incorporates and builds upon <a href="https://github.com/elisepegg/py_bonemat_abaqus">py_bonemat_abaqus</a>, which is licensed under GPLv3, and therefore this project adopts the same license to remain compliant.

