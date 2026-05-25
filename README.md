![visitors](https://visitor-badge.laobi.icu/badge?page_id=modenaxe.slicerbonemat)
# SlicerBoneMat

This is a 3D Slicer extension for assigning material properties (specifically Young's Modulus) to volumetric meshes using CT voxel intensities.

It's designed to be a modern, open-source equivalent of the original BoneMat software, with some much-needed improvements to the UI, supported I/O formats and phantom calibration abilities.

![Alt text](Screenshot01.png?raw=true "Segment Mesher module user interface")

## Usage

A full extended tutorial is available in the `tutorial/README.md` file. Regardless, here is a brief description of how to use the various sections of the module's UI:
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
    * Tetrahedron quality (i.e. the radius-edge ratio)
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
    * The number of integration steps refers to how many integration points the application will set in each element (when integrating using the v2 or v3 algorithms)
    * The gap value is the gap between the bins that the Young's modulus values are grouped into
* Apply
  * This will begin the main mapping procedure
  * A progress bar will appear which gives an indication of the mapping procedure's progress
    * Note that because the mapping procedure happens on the main UI thread within Slicer, the application will be unresponsive until mapping is complete.
  * The elapsed time of the process will be displayed in the text box below
* Download options
  * The extension currently supports 4 output formats, including:
    * VTK
    * ABAQUS
    * ANSYS
    * FEBio

## License

This project is released under the GNU General Public License v3 (GPLv3). While Slicer typically prefers more permissive licenses, this module incorporates and builds upon <a href="https://github.com/elisepegg/py_bonemat_abaqus">py_bonemat_abaqus</a>, developed by Dr Elise Pegg (University of Bath), which is licensed under GPLv3, and therefore this project adopts the same license to remain compliant.

# Sample data

The tutorial CT images were obtained from the MITK-GEM website, available <a href="https://github.com/araex/mitk-gem-site/tree/gh-pages/tutorial_files">here</a>. The segmentation was performed manually by the authors using MITK-GEM.
