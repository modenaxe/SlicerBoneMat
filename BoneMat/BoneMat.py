import os
import sys
import re
import math
from typing import Optional
from __main__ import qt

import vtk
from vtk.util import numpy_support
from vtkmodules.vtkFiltersVerdict import vtkMeshQuality
import numpy as np
import json
import tempfile
import importlib
from pathlib import Path

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)
from slicer import (
    vtkMRMLScalarVolumeNode,
    vtkMRMLModelNode
)

def ensureLocalPackage(importName, installPath=None):
    try:
        return importlib.import_module(importName)
    except ModuleNotFoundError:
        if installPath:
            slicer.util.pip_install(installPath)
        else:
            slicer.util.pip_install(f"\"{importName}\"")
        importlib.invalidate_caches()
        return importlib.import_module(importName)
    
ensureLocalPackage('meshio')

import meshio
    
def configurePyBonematImports(module_file):
    project_root = os.path.abspath(os.path.join(os.path.dirname(module_file), ".."))
    bonemat_repo_root = os.path.join(project_root, "external/py_bonemat_abaqus")

    if bonemat_repo_root in sys.path:
        sys.path.remove(bonemat_repo_root)
    sys.path.insert(0, bonemat_repo_root)

    if project_root in sys.path:
        sys.path.remove(project_root)
        sys.path.append(project_root)

    if "py_bonemat_abaqus" in sys.modules:
        del sys.modules["py_bonemat_abaqus"]

    importlib.invalidate_caches()
    
#
# BoneMat
#


class BoneMat(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("BoneMat")
        self.parent.categories = ["Surface Models"]
        self.parent.dependencies = []
        self.parent.contributors = ["Maxwell Hogan (University of New South Wales)", "Luca Modenese (University of New South Wales)"]
        self.parent.helpText = _("""
Generate finite element models from CT data with automated material mapping based on voxel intensities.
<p>This module is intended to be a 3D Slicer implementation of the <a href="https://ior-bic.github.io/software/bonemat/index.html">original BoneMat software</a>, which was created by the Bioengineering and Computing Laboratory (BIC) of the Rizzoli Orthopaedic Institute (Bologna, Italy). This extension is powered by a Python implementation of BoneMat, <a href="https://github.com/elisepegg/py_bonemat_abaqus/tree/master">'py_bonemat_abaqus'</a>, written by Dr Elise Pegg (Newcastle University) in 2016, created to add ABAQUS mesh support to the original software.</p>
""")
        self.parent.acknowledgementText = _("""
The idea for this module was conceived by Dr Luca Modenese (University of New South Wales) as a modern, open-source implementation of BoneMat which supported more operating systems and I/O formats. The module itself was developed by Maxwell Hogan (University of New South Wales) as part of a Software Engineering Honours Thesis project under Dr Modenese's supervision.
<p>BoneMat citation: Taddei F, Schileo E, Helgason B, Cristofolini L, Viceconti M. The material mapping strategy influences the accuracy of CT-based finite element models of bones: an evaluation against experimental measurements. Med Eng Phys. 2007 Nov;29(9):973-9</p>
<p>py_bonemat_abaqus citation: Elise C. Pegg, Harinderjit S. Gill, An open source software tool to assign the material properties of bone for ABAQUS finite element simulations, Journal of Biomechanics, Volume 49, Issue 13, 2016, Pages 3116-3121</p>
""")

#
# BoneMatParameterNode
#

@parameterNodeWrapper
class BoneMatParameterNode:
    """
    The parameters needed by module.

    inputVolume - The volume to threshold.
    imageThreshold - The value at which to threshold the input volume.
    invertThreshold - If true, will invert the threshold.
    thresholdedVolume - The output volume that will contain the thresholded volume.
    invertedVolume - The output volume that will contain the inverted thresholded volume.
    """

    inputCT: vtkMRMLScalarVolumeNode
    inputVolMesh: vtkMRMLModelNode
    outputVolMesh: vtkMRMLModelNode

    meshNodes: str
    meshElements: str
    meshMinStat: str
    meshMaxStat: str
    meshAvgStat: str

    ctDensitySlope: float
    ctDensityIntercept: float
    ashDensityOffset: float
    ashDensityScale: float
    apparentDensityDivisor: float
    modulusScale: float
    modulusExponent: float

    valuesPreset: str
    minModulus: float
    poissonValue: float
    gapValue: int
    ctPadDepth: int
    ctPadValue: int
    downloadFormat: str

#
# BoneMatWidget
#

class BoneMatWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/BoneMat.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = BoneMatLogic()

        # Setup input mesh statistics options
        self.ui.inputMeshStatSelector.addItem('Element volume', 'vol')
        self.ui.inputMeshStatSelector.addItem('Tetrahedron quality', 'tet_quality')
        self.ui.inputMeshStatSelector.addItem('Maximum element edge length', 'max_edge')
        self.ui.inputMeshStatSelector.addItem('Minimum element edge length', 'min_edge')

        # Setup download formats
        self.ui.downloadFormatSelector.addItem('VTK', '.vtk')
        self.ui.downloadFormatSelector.addItem('FEBio (.feb)', '.feb')
        self.ui.downloadFormatSelector.addItem('Abaqus (.inp)', '.inp')
        self.ui.downloadFormatSelector.addItem('Ansys (.cdb)', '.cdb')
        self.ui.downloadFormatSelector.setCurrentIndex(0)

        # Setup algorithm choices
        self.ui.algoSelector.addItem('HU averaging (Bonemat v1)', 'None')
        self.ui.algoSelector.addItem('HU integration (Bonemat v2)', 'HU')
        self.ui.algoSelector.addItem('E integration (Bonemat v3)', 'E')
        self.ui.algoSelector.setCurrentIndex(2)

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Combo Boxes
        self.ui.inputVolMeshSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onInputMeshSelection)
        self.ui.inputMeshStatSelector.connect("currentIndexChanged(int)", self.onMeshStatSelection)
        self.ui.presetSelector.connect("currentIndexChanged(int)", self.onPresetSelection)

        # Buttons
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)
        self.ui.downloadVTKButton.connect("clicked(bool)", self.onDownloadButton)
        self.ui.savePresetButton.connect("clicked(bool)", self.onSavePresetButton)
        self.ui.deletePresetButton.connect("clicked(bool)", self.onDeletePresetButton)
        self.ui.calcMeshStatsButton.connect("clicked(bool)", self.onCalcMeshStatsButton)

        # Checkboxes
        self.ui.phantomCalibrationCheckBox.connect("clicked(bool)", self.onPhantomCheckBox)

        # Phantom calibration table
        self.ui.phantomCalibrationTableWidget.connect("cellChanged(int,int)", self.onPhantomCellChange)

        # Adjusting the UI of the phantom calibration table
        table = self.ui.phantomCalibrationTableWidget
        table.horizontalHeader().setSectionResizeMode(qt.QHeaderView.Stretch)

        height = table.horizontalHeader().height
        for row in range(table.rowCount):
            height += table.rowHeight(row)
        height += table.frameWidth * 2
        table.setFixedHeight(height)

        # Phantom calibration is initially inactive
        self.ui.phantomCalibrationTableWidget.enabled = False

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

        self.ui.inputMeshStatSelector.setCurrentIndex(0)

        self.setBoneDensityPresetValues()

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()

        # Combo Boxes
        self.ui.inputVolMeshSelector.disconnect("currentNodeChanged(vtkMRMLNode*)", self.onInputMeshSelection)
        self.ui.inputMeshStatSelector.disconnect("currentIndexChanged(int)", self.onMeshStatSelection)
        self.ui.presetSelector.disconnect("currentIndexChanged(int)", self.onPresetSelection)

        # Buttons
        self.ui.applyButton.disconnect("clicked(bool)", self.onApplyButton)
        self.ui.downloadVTKButton.disconnect("clicked(bool)", self.onDownloadButton)
        self.ui.savePresetButton.disconnect("clicked(bool)", self.onSavePresetButton)
        self.ui.deletePresetButton.disconnect("clicked(bool)", self.onDeletePresetButton)
        self.ui.calcMeshStatsButton.disconnect("clicked(bool)", self.onCalcMeshStatsButton)

        # Checkboxes
        self.ui.phantomCalibrationCheckBox.disconnect("clicked(bool)", self.onPhantomCheckBox)

        # Phantom calibration table
        self.ui.phantomCalibrationTableWidget.disconnect("cellChanged(int,int)", self.onPhantomCellChange)

    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # Default values for some options
        with slicer.util.NodeModify(self._parameterNode):
            self._parameterNode.meshNodes = '0'
            self._parameterNode.meshElements = '0'
            self._parameterNode.meshMinStat = '0'
            self._parameterNode.meshMaxStat = '0'
            self._parameterNode.meshAvgStat = '0'

            self._parameterNode.minModulus = 10
            self._parameterNode.poissonValue = 0.35
            self._parameterNode.gapValue = 200
            self._parameterNode.ctPadDepth = 1
            self._parameterNode.ctPadValue = -1000

    def setParameterNode(self, inputParameterNode: Optional[BoneMatParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
            self._checkCanApply()

    def _checkCanApply(self, caller=None, event=None) -> None:
        if self._parameterNode and self._parameterNode.inputCT and self._parameterNode.inputVolMesh and self._parameterNode.outputVolMesh:
            self.ui.applyButton.toolTip = _("Commence material property assignment")
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = _("Select input CT, input mesh and output mesh")
            self.ui.applyButton.enabled = False

    def setBoneDensityPresetValues(self) -> None:
        settings = qt.QSettings()
        jsonPresets = settings.value('BoneMat/BoneDensityPresets')
        presets = None
        try:
            if jsonPresets is None:
                raise Exception()
            presets = json.loads(jsonPresets)
        except:
            # no presets initialised, or object wasn't valid json
            # write a 'None' preset with 0s as the 7 values
            presets = {
                'None': {
                    'ctDensitySlope': 0,
                    'ctDensityIntercept': 0,
                    'ashDensityOffset': 0,
                    'ashDensityScale': 0,
                    'apparentDensityDivisor': 0,
                    'modulusScale': 0,
                    'modulusExponent': 0
                }
            }
            settings.setValue('BoneMat/BoneDensityPresets', json.dumps(presets))

        for name, values in presets.items():
            self.ui.presetSelector.addItem(name, values)

        index = self.ui.presetSelector.findText('Femur')
        if index == -1:
            index = self.ui.presetSelector.findText('None')
        self.ui.presetSelector.setCurrentIndex(index)

    def onPresetSelection(self) -> None:
        values = self.ui.presetSelector.currentData

        self._parameterNode.ctDensitySlope = values['ctDensitySlope']
        self._parameterNode.ctDensityIntercept = values['ctDensityIntercept']
        self._parameterNode.ashDensityOffset = values['ashDensityOffset']
        self._parameterNode.ashDensityScale = values['ashDensityScale']
        self._parameterNode.apparentDensityDivisor = values['apparentDensityDivisor']
        self._parameterNode.modulusScale = values['modulusScale']
        self._parameterNode.modulusExponent = values['modulusExponent']

    def onInputMeshSelection(self) -> None:
        with slicer.util.NodeModify(self._parameterNode):
            self._parameterNode.meshNodes = '0'
            self._parameterNode.meshElements = '0'
            self._parameterNode.meshMinStat = '0'
            self._parameterNode.meshMaxStat = '0'
            self._parameterNode.meshAvgStat = '0'

        self._meshStats = {}
        self._meshStats["meshMinVol"] = 0
        self._meshStats["meshMaxVol"] = 0
        self._meshStats["meshAvgVol"] = 0
        self._meshStats["meshMinTetQual"] = 0
        self._meshStats["meshMaxTetQual"] = 0
        self._meshStats["meshAvgTetQual"] = 0
        self._meshStats["meshMinMinEdge"] = 0
        self._meshStats["meshMaxMinEdge"] = 0
        self._meshStats["meshAvgMinEdge"] = 0
        self._meshStats["meshMinMaxEdge"] = 0
        self._meshStats["meshMaxMaxEdge"] = 0
        self._meshStats["meshAvgMaxEdge"] = 0

        self._plots = {}
        self.ui.inputMeshStatsPlotView.setMinimumHeight(0)

    def onCalcMeshStatsButton(self) -> None:
        mesh = self._parameterNode.inputVolMesh
        if mesh is None:
            return
        
        self.ui.calcMeshStatsButton.enabled = False
        self.ui.calcMeshStatsButton.text = 'Loading...'
        slicer.app.processEvents()
        
        ugrid = mesh.GetUnstructuredGrid()
        mq = vtkMeshQuality()
        volume = []
        tetQuality = []
        minEdge = []
        maxEdge = []

        for i in range(ugrid.GetNumberOfCells()):
            cell = ugrid.GetCell(i)

            if cell.GetCellType() in [vtk.VTK_TETRA, vtk.VTK_QUADRATIC_TETRA]:
                volume.append(mq.TetVolume(cell))
                tetQuality.append(self.computeTetQuality(cell))
            elif cell.GetCellType() in [vtk.VTK_PYRAMID]:
                volume.append(mq.PyramidVolume(cell))
            elif cell.GetCellType() in [vtk.VTK_WEDGE]:
                volume.append(mq.WedgeVolume(cell))
            elif cell.GetCellType() in [vtk.VTK_HEXAHEDRON, vtk.VTK_QUADRATIC_HEXAHEDRON, vtk.VTK_TRIQUADRATIC_HEXAHEDRON]:
                volume.append(mq.HexVolume(cell))
            else:
                continue

            squareEdgeLens = []
            for e in range(cell.GetNumberOfEdges()):
                pts = cell.GetEdge(e).GetPoints()
                p1 = pts.GetPoint(0)
                p2 = pts.GetPoint(1)
                squareEdgeLens.append(
                    (p1[0] - p2[0]) ** 2 +
                    (p1[1] - p2[1]) ** 2 +
                    (p1[2] - p2[2]) ** 2
                )

            minEdge.append(np.sqrt(np.min(squareEdgeLens)))
            maxEdge.append(np.sqrt(np.max(squareEdgeLens)))

        self._parameterNode.meshNodes = str(ugrid.GetNumberOfPoints())
        self._parameterNode.meshElements = str(ugrid.GetNumberOfCells())

        self._meshStats["meshMinVol"] = np.min(volume)
        self._meshStats["meshMaxVol"] = np.max(volume)
        self._meshStats["meshAvgVol"] = np.mean(volume)

        self._meshStats["meshMinTetQual"] = np.min(tetQuality)
        self._meshStats["meshMaxTetQual"] = np.max(tetQuality)
        self._meshStats["meshAvgTetQual"] = np.mean(tetQuality)

        self._meshStats["meshMinMinEdge"] = np.min(minEdge)
        self._meshStats["meshMaxMinEdge"] = np.max(minEdge)
        self._meshStats["meshAvgMinEdge"] = np.mean(minEdge)

        self._meshStats["meshMinMaxEdge"] = np.min(maxEdge)
        self._meshStats["meshMaxMaxEdge"] = np.max(maxEdge)
        self._meshStats["meshAvgMaxEdge"] = np.mean(maxEdge)

        self.ui.calcMeshStatsButton.enabled = True
        self.ui.calcMeshStatsButton.text = 'Calculate'

        self.createMeshStatsPlots(volume, tetQuality, minEdge, maxEdge)

        self.onMeshStatSelection()

    def createMeshStatsPlots(self, volume, tetQuality, minEdge, maxEdge) -> None:
        volumeTable = self.createMeshStatTable(volume)
        tetQualityTable = self.createMeshStatTable(tetQuality)
        minEdgeTable = self.createMeshStatTable(minEdge)
        maxEdgeTable = self.createMeshStatTable(maxEdge)

        # Get chart from widget
        chartView = self.ui.inputMeshStatsPlotView
        chart = chartView.chart()
        chart.ClearPlots()

        self._plots = {}

        self._plots["volume"] = chart.AddPlot(vtk.vtkChart.BAR)
        self._plots["volume"].SetInputData(volumeTable, 0, 1)

        self._plots["tetQuality"] = chart.AddPlot(vtk.vtkChart.BAR)
        self._plots["tetQuality"].SetInputData(tetQualityTable, 0, 1)

        self._plots["minEdge"] = chart.AddPlot(vtk.vtkChart.BAR)
        self._plots["minEdge"].SetInputData(minEdgeTable, 0, 1)

        self._plots["maxEdge"] = chart.AddPlot(vtk.vtkChart.BAR)
        self._plots["maxEdge"].SetInputData(maxEdgeTable, 0, 1)

        chartView.setMinimumHeight(250)

    def createMeshStatTable(self, values):
        counts, edges = np.histogram(values, bins=20)
        centres = 0.5 * (edges[:-1] + edges[1:])

        table = vtk.vtkTable()
        xArr = vtk.vtkFloatArray()
        xArr.SetName("Volume")
        yArr = vtk.vtkIntArray()
        yArr.SetName("Count")

        for x, y in zip(centres, counts):
            xArr.InsertNextValue(x)
            yArr.InsertNextValue(y)

        table.AddColumn(xArr)
        table.AddColumn(yArr)
        return table

    def onMeshStatSelection(self) -> None:
        stat = self.ui.inputMeshStatSelector.currentData
        if self._parameterNode.inputVolMesh is None or self._plots == {}:
            return

        self._plots["volume"].SetVisible(stat == 'vol')
        self._plots["tetQuality"].SetVisible(stat == 'tet_quality')
        self._plots["minEdge"].SetVisible(stat == 'min_edge')
        self._plots["maxEdge"].SetVisible(stat == 'max_edge')

        chartView = self.ui.inputMeshStatsPlotView
        chart = chartView.chart()

        chart.GetAxis(vtk.vtkAxis.LEFT).SetTitle('Number of Elements')
        chart.RecalculateBounds()

        chartView.setAxesToChartBounds()
        chartView.renderWindow().Render()

        if stat == 'vol':
            chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle('Element Volume')
            with slicer.util.NodeModify(self._parameterNode):
                self._parameterNode.meshMinStat = str(round(self._meshStats["meshMinVol"], 6))
                self._parameterNode.meshMaxStat = str(round(self._meshStats["meshMaxVol"], 6))
                self._parameterNode.meshAvgStat = str(round(self._meshStats["meshAvgVol"], 6))
        elif stat == 'tet_quality':
            chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle('Tetrahedron Quality')
            with slicer.util.NodeModify(self._parameterNode):
                self._parameterNode.meshMinStat = str(round(self._meshStats["meshMinTetQual"], 6))
                self._parameterNode.meshMaxStat = str(round(self._meshStats["meshMaxTetQual"], 6))
                self._parameterNode.meshAvgStat = str(round(self._meshStats["meshAvgTetQual"], 6))
        elif stat == 'min_edge':
            chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle('Minimum Element Edge Length')
            with slicer.util.NodeModify(self._parameterNode):
                self._parameterNode.meshMinStat = str(round(self._meshStats["meshMinMinEdge"], 6))
                self._parameterNode.meshMaxStat = str(round(self._meshStats["meshMaxMinEdge"], 6))
                self._parameterNode.meshAvgStat = str(round(self._meshStats["meshAvgMinEdge"], 6))
        elif stat == 'max_edge':
            chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle('Maximum Element Edge Length')
            with slicer.util.NodeModify(self._parameterNode):
                self._parameterNode.meshMinStat = str(round(self._meshStats["meshMinMaxEdge"], 6))
                self._parameterNode.meshMaxStat = str(round(self._meshStats["meshMaxMaxEdge"], 6))
                self._parameterNode.meshAvgStat = str(round(self._meshStats["meshAvgMaxEdge"], 6))

    # Calculates radius-edge ratio of tets
    # Transcribes the FEBio Studio source code's C++ implementation
    def computeTetQuality(self, cell) -> float:
        points = cell.GetPoints()

        # Read the first 4 nodal coordinates
        p = [points.GetPoint(i) for i in range(4)]

        # Build matrix A
        A = [
            [p[1][0] - p[0][0], p[1][1] - p[0][1], p[1][2] - p[0][2]],
            [p[2][0] - p[0][0], p[2][1] - p[0][1], p[2][2] - p[0][2]],
            [p[3][0] - p[0][0], p[3][1] - p[0][1], p[3][2] - p[0][2]],
        ]

        # Determinant of A
        detA = (
            A[0][0] * (A[1][1] * A[2][2] - A[1][2] * A[2][1])
            - A[0][1] * (A[1][0] * A[2][2] - A[1][2] * A[2][0])
            + A[0][2] * (A[1][0] * A[2][1] - A[1][1] * A[2][0])
        )

        eps = 1e-14
        if abs(detA) < eps:
            return math.inf

        inv_det = 1.0 / detA

        # Inverse of A
        Ainv = [
            [
                (A[1][1] * A[2][2] - A[1][2] * A[2][1]) * inv_det,
                -(A[0][1] * A[2][2] - A[0][2] * A[2][1]) * inv_det,
                (A[0][1] * A[1][2] - A[0][2] * A[1][1]) * inv_det,
            ],
            [
                -(A[1][0] * A[2][2] - A[1][2] * A[2][0]) * inv_det,
                (A[0][0] * A[2][2] - A[0][2] * A[2][0]) * inv_det,
                -(A[0][0] * A[1][2] - A[0][2] * A[1][0]) * inv_det,
            ],
            [
                (A[1][0] * A[2][1] - A[1][1] * A[2][0]) * inv_det,
                -(A[0][0] * A[2][1] - A[0][1] * A[2][0]) * inv_det,
                (A[0][0] * A[1][1] - A[0][1] * A[1][0]) * inv_det,
            ],
        ]

        def squared_norm(v):
            return v[0] * v[0] + v[1] * v[1] + v[2] * v[2]

        # Build RHS b
        b = [
            0.5 * (squared_norm(p[1]) - squared_norm(p[0])),
            0.5 * (squared_norm(p[2]) - squared_norm(p[0])),
            0.5 * (squared_norm(p[3]) - squared_norm(p[0])),
        ]

        # Circumcenter c = Ainv * b
        c = [
            Ainv[0][0] * b[0] + Ainv[0][1] * b[1] + Ainv[0][2] * b[2],
            Ainv[1][0] * b[0] + Ainv[1][1] * b[1] + Ainv[1][2] * b[2],
            Ainv[2][0] * b[0] + Ainv[2][1] * b[1] + Ainv[2][2] * b[2],
        ]

        # Circumradius
        dx = p[0][0] - c[0]
        dy = p[0][1] - c[1]
        dz = p[0][2] - c[2]
        R = math.sqrt(dx * dx + dy * dy + dz * dz)

        # Shortest of the 6 tet edges
        edges = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))

        min_L2 = float("inf")
        for j, k in edges:
            ex = p[j][0] - p[k][0]
            ey = p[j][1] - p[k][1]
            ez = p[j][2] - p[k][2]
            L2 = ex * ex + ey * ey + ez * ez
            if L2 < min_L2:
                min_L2 = L2

        if min_L2 < eps:
            return math.inf

        L = math.sqrt(min_L2)

        return R / L

    def onSavePresetButton(self) -> None:
        name = qt.QInputDialog().getText(None, 'Save', 'Save preset as: (will override an existing preset with the same name)')
        if name is None or name == '':
            return
        if name == 'None':
            message = qt.QMessageBox()
            message.setText('"None" is a reserved preset name, choose another name')
            message.exec()
            return
        
        newPresetValues = {
            'ctDensitySlope': self._parameterNode.ctDensitySlope,
            'ctDensityIntercept': self._parameterNode.ctDensityIntercept,
            'ashDensityOffset': self._parameterNode.ashDensityOffset,
            'ashDensityScale': self._parameterNode.ashDensityScale,
            'apparentDensityDivisor': self._parameterNode.apparentDensityDivisor,
            'modulusScale': self._parameterNode.modulusScale,
            'modulusExponent': self._parameterNode.modulusExponent
        }
        
        settings = qt.QSettings()
        presets = json.loads(settings.value('BoneMat/BoneDensityPresets'))
        presets[name] = newPresetValues
        settings.setValue('BoneMat/BoneDensityPresets', json.dumps(presets))

        self.ui.presetSelector.addItem(name, newPresetValues)
        index = self.ui.presetSelector.findText(name)
        self.ui.presetSelector.setCurrentIndex(index)
    
    def onDeletePresetButton(self) -> None:
        presetName = self.ui.presetSelector.currentText
        if presetName == 'None':
            message = qt.QMessageBox()
            message.setText('Cannot delete "None" preset')
            message.exec()
            return
        
        settings = qt.QSettings()
        presets = json.loads(settings.value('BoneMat/BoneDensityPresets'))
        presets.pop(presetName)
        settings.setValue('BoneMat/BoneDensityPresets', json.dumps(presets))

        currIndex = self.ui.presetSelector.findText(presetName)
        self.ui.presetSelector.removeItem(currIndex)
        noneIndex = self.ui.presetSelector.findText('None')
        self.ui.presetSelector.setCurrentIndex(noneIndex)

    def onApplyButton(self) -> None:
        """Run processing when user clicks "Apply" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
            # Compute output
            self.logic.process(
                self._parameterNode.inputCT,
                self._parameterNode.inputVolMesh,
                self._parameterNode.outputVolMesh,
                self.ui.algoSelector.currentData
            )

    def exportAbaqusMesh(self, ugrid, filePath) -> None:
        lines = [
            '*Heading\n',
            'Abaqus DataFile Version 6.14\n',
            'written by Maxwell Hogan\n',
            '*Node\n'
        ]
        
        pts = ugrid.GetPoints()
        for ptId in range(ugrid.GetNumberOfPoints()):
            pt = pts.GetPoint(ptId)
            lines.append(f'{ptId+1}, {pt[0]:.10e}, {pt[1]:.10e}, {pt[2]:.10e}\n')

        ptsToCellType = {
            f'{vtk.VTK_TETRA}': 'C3D4',
            f'{vtk.VTK_QUADRATIC_TETRA}': 'C3D10',
            f'{vtk.VTK_WEDGE}': 'C3D6',
            f'{vtk.VTK_HEXAHEDRON}': 'C3D8'
        }
        # assumes mesh is homogenous
        lines.append(f'*Element,type={ptsToCellType[str(ugrid.GetCell(0).GetCellType())]}\n')

        for cellId in range(ugrid.GetNumberOfCells()):
            ptIds = ugrid.GetCell(cellId).GetPointIds()
            elementLine = str(cellId+1)
            for i in range(ptIds.GetNumberOfIds()):
                elementLine += f',{ptIds.GetId(i) + 1}'
            lines.append(elementLine + '\n')

        vtkModuli = ugrid.GetCellData().GetAbstractArray('YoungsModulus')
        if vtkModuli is None:
            slicer.util.errorDisplay('Output model has no attached Young\'s Modulus data')
            return
        
        moduli = numpy_support.vtk_to_numpy(vtkModuli)
        modSet = np.sort(np.unique(moduli))
        indexToMod = {i+1: value for i, value in enumerate(modSet)}.items()

        modToCells = {i: [] for i in modSet}
        for cellId, mod in enumerate(moduli):
            modToCells[mod] += [cellId + 1]

        for elsetNum, mod in indexToMod:
            lines.append(f'*Elset, elset=BoneMat_ModBin_{elsetNum}\n')
            elsetCells = modToCells[mod]
            i = 0
            while i < len(elsetCells):
                lines.append(','.join(list(map(str, elsetCells[i:i+16]))) + '\n')
                i += 16

        for elsetNum, mod in indexToMod:
            lines.append(f'*Solid Section, elset=BoneMat_ModBin_{elsetNum}, material=BoneMat_{elsetNum}\n')

        lines.extend(['**\n', '** MATERIALS\n', '**\n'])

        for matNum, mod in indexToMod:
            lines.extend([
                f'*Material, name=BoneMat_{matNum}\n',
                '*Elastic\n',
                f'{mod}, {self._parameterNode.poissonValue}\n'
            ])

        with open(filePath, 'w') as f:
            f.writelines(lines)

    def exportFebioMesh(self, ugrid, filePath) -> None:
        lines = [
            '<?xml version="1.0" encoding="ISO-8859-1"?>\n',
            '<febio_spec version="4.0">\n'
        ]

        # Assume we'll be doing a structural mechanics analysis
        lines.append('\t<Module type="solid"/>\n')

        vtkModuli = ugrid.GetCellData().GetAbstractArray('YoungsModulus')
        if vtkModuli is None:
            slicer.util.errorDisplay('Output model has no attached Young\'s Modulus data')
            return
        
        moduli = numpy_support.vtk_to_numpy(vtkModuli)
        modSet = np.sort(np.unique(moduli))
        indexToMod = {i+1: value for i, value in enumerate(modSet)}.items()

        modToCells = {i: [] for i in modSet}
        for cellId, mod in enumerate(moduli):
            modToCells[mod] += [cellId]
        
        lines.extend([
            '\t<Material>\n',
            '\t\t<material id="1" name="youngs_modulus" type="isotropic elastic">\n',
            '\t\t\t<E type="map">moduli_map</E>\n',
            f'\t\t\t<v>{self._parameterNode.poissonValue}</v>\n',
            '\t\t</material>\n'
            '\t</Material>\n'
        ])

        lines.append('\t<Mesh>\n')
        lines.append('\t\t<Nodes>\n')
        pts = ugrid.GetPoints()
        for ptId in range(ugrid.GetNumberOfPoints()):
            pt = pts.GetPoint(ptId)
            lines.append(f'\t\t\t<node id="{ptId+1}">{pt[0]:.10e},{pt[1]:.10e},{pt[2]:.10e}</node>\n')
        lines.append('\t\t</Nodes>\n')

        ptsToCellType = {
            f'{vtk.VTK_TETRA}': 'tet4',
            f'{vtk.VTK_QUADRATIC_TETRA}': 'tet10',
            f'{vtk.VTK_WEDGE}': 'penta6',
            f'{vtk.VTK_HEXAHEDRON}': 'hex8'
        }
        for elementId, mod in indexToMod:
            # Assumes all elements with same modulus have the same cell type
            cellIds = modToCells[mod]
            cellType = ptsToCellType[str(ugrid.GetCell(cellIds[0]).GetCellType())]
            lines.append(f'\t\t<Elements type="{cellType}" name="BoneMat_Set_{elementId}">\n')
            for cellId in cellIds:
                ptIdsList = ugrid.GetCell(cellId).GetPointIds()
                elementLine = f'\t\t\t<elem id="{cellId+1}">'
                ptIds = list(map(lambda x: str(ptIdsList.GetId(x) + 1), range(ptIdsList.GetNumberOfIds())))
                elementLine += ','.join(ptIds) + '</elem>\n'
                lines.append(elementLine)
            lines.append('\t\t</Elements>\n')
        lines.append('\t</Mesh>\n')

        lines.append('\t<MeshDomains>\n')
        for num, mod in indexToMod:
            lines.append(f'\t\t<SolidDomain name="BoneMat_Set_{num}" mat="youngs_modulus"/>\n')
        lines.append('\t</MeshDomains>\n')

        lines.append('\t<MeshData>\n')
        for elementId, mod in indexToMod:
            lines.append(f'\t\t<ElementData name="moduli_map" elem_set="BoneMat_Set_{elementId}">\n')
            numCells = len(modToCells[mod])
            for i in range(numCells):
                lines.append(f'\t\t\t<elem lid="{i+1}">{mod}</elem>\n')
            lines.append(f'\t\t</ElementData>\n')
        lines.append('\t</MeshData>\n')

        lines.append('</febio_spec>\n')
        with open(filePath, 'w') as f:
            f.writelines(lines)

    def exportAnsysMesh(self, ugrid, filePath) -> None:
        lines = ['/PREP7\n\n']

        ptsToCellType = {
            f'{vtk.VTK_TETRA}': 'SOLID285',
            f'{vtk.VTK_QUADRATIC_TETRA}': 'SOLID187',
            f'{vtk.VTK_WEDGE}': 'SOLID185',
            f'{vtk.VTK_HEXAHEDRON}': 'SOLID185'
        }
        # Assumes mesh is homogenous
        lines.extend([
            f'ET,1,{ptsToCellType[str(ugrid.GetCell(0).GetCellType())]}\n',
            'TYPE,1\n\n'
        ])

        vtkModuli = ugrid.GetCellData().GetAbstractArray('YoungsModulus')
        if vtkModuli is None:
            slicer.util.errorDisplay('Output model has no attached Young\'s Modulus data')
            return

        moduli = numpy_support.vtk_to_numpy(vtkModuli)
        modSet = np.sort(np.unique(moduli))
        indexToMod = {i+1: value for i, value in enumerate(modSet)}.items()

        for matNum, mod in indexToMod:
            lines.extend([
                f'MP,EX,{matNum},{mod}\n',
                f'MP,NUXY,{matNum},{self._parameterNode.poissonValue}\n\n'
            ])

        pts = ugrid.GetPoints()
        for ptId in range(ugrid.GetNumberOfPoints()):
            pt = pts.GetPoint(ptId)
            lines.append(f'N,{ptId+1},{pt[0]:.10e},{pt[1]:.10e},{pt[2]:.10e}\n')

        modToCells = {i: [] for i in modSet}
        for cellId, mod in enumerate(moduli):
            modToCells[mod] += [cellId]

        for matNum, mod in indexToMod:
            lines.append(f'\nMAT,{matNum}\n')
            for cellId in modToCells[mod]:
                ptIdsList = ugrid.GetCell(cellId).GetPointIds()
                ptIds = list(map(lambda x: str(ptIdsList.GetId(x) + 1), range(ptIdsList.GetNumberOfIds())))
                lines.append('E,' + ','.join(ptIds) + '\n')

        with open(filePath, 'w') as f:
            f.writelines(lines)

    def onDownloadButton(self) -> None:
        outputModel = self._parameterNode.outputVolMesh
        if not outputModel:
            slicer.util.errorDisplay('No output model available to export')
            return
        
        format = self.ui.downloadFormatSelector.currentText
        downloadExt = self.ui.downloadFormatSelector.currentData
        
        filePath = qt.QFileDialog.getSaveFileName(
            slicer.util.mainWindow(),
            "Save mesh as " + format,
            slicer.app.defaultScenePath
        )

        if not filePath:
            return

        try:
            root, ext = os.path.splitext(filePath)
            if ext.lower() != downloadExt:
                filePath = root + downloadExt

            if downloadExt == '.vtk':
                ugridWriter = vtk.vtkUnstructuredGridWriter()
                ugridWriter.SetFileName(filePath)
                ugridWriter.SetInputData(outputModel.GetUnstructuredGrid())
                ugridWriter.SetFileTypeToASCII()
                ugridWriter.Write()
            elif downloadExt == '.inp':
                self.exportAbaqusMesh(outputModel.GetUnstructuredGrid(), filePath)
            elif downloadExt == '.feb':
                self.exportFebioMesh(outputModel.GetUnstructuredGrid(), filePath)
            elif downloadExt == '.cdb':
                self.exportAnsysMesh(outputModel.GetUnstructuredGrid(), filePath)
            
            slicer.util.infoDisplay(f"Mesh saved to: {filePath}")
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to save mesh: {e}")

    def onPhantomCheckBox(self, checked) -> None:
        if checked:
            self.ui.phantomCalibrationTableWidget.enabled = True
            self.ui.ctDensitySlopeSpinBox.enabled = False
            self.ui.ctDensityInterceptSpinBox.enabled = False
        else:
            self.ui.phantomCalibrationTableWidget.enabled = False
            self.ui.ctDensitySlopeSpinBox.enabled = True
            self.ui.ctDensityInterceptSpinBox.enabled = True

    def onPhantomCellChange(self, row, col) -> None:
        table = self.ui.phantomCalibrationTableWidget

        try:
            float(table.item(row, col).text())
        except ValueError:
            table.item(row, col).setText('')
            return
        
        cellItems = [table.item(0, 0), table.item(0, 1), table.item(1, 0), table.item(1, 1)]
        if len([x for x in cellItems if x is not None and x.text() != '']) < 4:
            return
        
        nums = [float(x.text()) for x in cellItems]
        slope = (nums[1] - nums[3]) / (nums[0] - nums[2])
        intercept = nums[1] - slope * nums[0]

        self.ui.ctDensitySlopeSpinBox.value = slope / 1000
        self.ui.ctDensityInterceptSpinBox.value = intercept / 1000

#
# BoneMatLogic
#


class BoneMatLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return BoneMatParameterNode(super().getParameterNode())

    def displayOutputMesh(self, mesh):
        displayNode = mesh.GetDisplayNode()
        if not displayNode:
            displayNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelDisplayNode')
            mesh.SetAndObserveDisplayNodeID(displayNode.GetID())

        # colour the mesh by YoungsModulus value
        displayNode.SetScalarVisibility(True)
        displayNode.SetActiveScalar('YoungsModulus', vtk.vtkAssignAttribute.CELL_DATA)
        displayNode.SetScalarRangeFlag(displayNode.UseDataScalarRange)

        # enable and tweak the colour legend for this display
        colourNode = slicer.util.getNode('DivergingBlueRed')
        if colourNode is not None:
            displayNode.SetAndObserveColorNodeID(colourNode.GetID())

        legendNode = slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(mesh)
        legendNode.SetVisibility(True)
        legendNode.SetNumberOfLabels(3)
        legendNode.SetTitleText('Young\'s Modulus')
        legendNode.SetLabelFormat('%.0f')
        legendNode.SetSize(0.1, 0.5)

        mesh.SetDisplayVisibility(True)

    def adjustAbaqusInput(self, in_path, out_path = None) -> str:
        """
        Fixes meshio ABAQUS output to match py_bonemat_abaqus expected format
        """

        in_path = str(in_path)
        out_path = str(out_path) if out_path else in_path

        lines = Path(in_path).read_text(encoding="utf-8", errors="replace").splitlines(True)

        out_lines = []
        inserted_part = False

        heading_re = re.compile(r"^(\s*)\*HEADING\b")
        node_re    = re.compile(r"^(\s*)\*NODE\b")
        elem_re    = re.compile(r"^(\s*)\*ELEMENT\s*,\s*TYPE\s*=", re.IGNORECASE)

        # py_bonemat_abaqus is strict about capitalisation, so we need multiple fixes
        for line in lines:
            # Replace *HEADING -> *Heading
            line = heading_re.sub(r"\1*Heading", line)

            # Insert *Part,name=model on the line before the first *NODE line
            if (not inserted_part) and node_re.match(line):
                indent = node_re.match(line).group(1)
                out_lines.append(f"{indent}*Part,name=model\n")
                inserted_part = True

            # Replace *NODE -> *Node
            line = node_re.sub(r"\1*Node", line)

            # Replace *ELEMENT, TYPE= -> *Element,type=
            line = elem_re.sub(r"\1*Element,type=", line)

            out_lines.append(line)

        # Add *End Part
        if out_lines and not out_lines[-1].endswith("\n"):
            out_lines[-1] += "\n"
        out_lines.append("*End Part\n")

        Path(out_path).write_text("".join(out_lines), encoding="utf-8")
        return out_path
    
    def reorderedPaddedScalars(self, img, flipX, flipY, flipZ):
        nx, ny, nz = img.GetDimensions()
        scalars = img.GetPointData().GetScalars()

        arr = numpy_support.vtk_to_numpy(scalars)

        # VTK point ordering: i fastest, then j, then k
        vol = arr.reshape((nz, ny, nx))

        if flipX:
            vol = vol[:, :, ::-1]
        if flipY:
            vol = vol[:, ::-1, :]
        if flipZ:
            vol = vol[::-1, :, :]

        # add user-specified voxel buffer of HU values around CT data
        paraNode = self.getParameterNode()
        if paraNode.ctPadDepth > 0:
            padShape = ((paraNode.ctPadDepth, paraNode.ctPadDepth),) * 3
            paddedVol = np.pad(vol, padShape, mode='constant', constant_values=paraNode.ctPadValue)
        else:
            paddedVol = vol

        arr2 = np.ascontiguousarray(paddedVol.reshape(-1))

        vtk_arr = numpy_support.numpy_to_vtk(
            num_array=arr2,
            deep=True,
            array_type=scalars.GetDataType()
        )
        vtk_arr.SetName(scalars.GetName())

        return vtk_arr
    
    def writeVolumeAsRectilinearGrid(self, volNode, outPath):
        """
        Writes a Slicer vtkMRMLScalarVolumeNode as a legacy VTK RECTILINEAR_GRID ASCII file
        with explicit X_COORDINATES / Y_COORDINATES / Z_COORDINATES and POINT_DATA scalars,
        as required by py_bonemat_abaqus.
        Assumes the volume axes are not obliquely rotated.
        """
        img = volNode.GetImageData()
        if img is None:
            raise ValueError("Volume node has no image data")

        nx, ny, nz = img.GetDimensions()

        ijkToRas = vtk.vtkMatrix4x4()
        volNode.GetIJKToRASMatrix(ijkToRas)

        def ras_of(i, j, k):
            v = [i, j, k, 1.0]
            out = [0.0, 0.0, 0.0, 1.0]
            ijkToRas.MultiplyPoint(v, out)
            return out[0], out[1], out[2]

        # Build coordinate arrays in ascending order
        xs = np.array([ras_of(i, 0, 0)[0] for i in range(nx)], dtype=np.float64)
        ys = np.array([ras_of(0, j, 0)[1] for j in range(ny)], dtype=np.float64)
        zs = np.array([ras_of(0, 0, k)[2] for k in range(nz)], dtype=np.float64)
        # Add extra coordinates at the front and back for padding later
        # assumes CT data is larger than a single voxel
        xDiff = xs[1] - xs[0]
        xs = np.concatenate(([xs[0] - xDiff], xs, [xs[nx - 1] + xDiff]))
        yDiff = ys[1] - ys[0]
        ys = np.concatenate(([ys[0] - yDiff], ys, [ys[ny - 1] + yDiff]))
        zDiff = zs[1] - zs[0]
        zs = np.concatenate(([zs[0] - zDiff], zs, [zs[nz - 1] + zDiff]))
        
        flipX = False
        flipY = False
        flipZ = False
        if xs[0] > xs[-1]:
            xs = xs[::-1]
            flipX = True
        if ys[0] > ys[-1]:
            ys = ys[::-1]
            flipY = True
        if zs[0] > zs[-1]:
            zs = zs[::-1]
            flipZ = True

        rg = vtk.vtkRectilinearGrid()
        dimPad = 2 * max(0, self.getParameterNode().ctPadDepth)
        rg.SetDimensions(nx + dimPad, ny + dimPad, nz + dimPad) # accounts for padding

        xArr = vtk.vtkDoubleArray()
        xArr.SetName("X_COORDINATES")
        xArr.SetNumberOfTuples(nx + dimPad)
        for i, v in enumerate(xs):
            xArr.SetValue(i, float(v))

        yArr = vtk.vtkDoubleArray()
        yArr.SetName("Y_COORDINATES")
        yArr.SetNumberOfTuples(ny + dimPad)
        for j, v in enumerate(ys):
            yArr.SetValue(j, float(v))

        zArr = vtk.vtkDoubleArray()
        zArr.SetName("Z_COORDINATES")
        zArr.SetNumberOfTuples(nz + dimPad)
        for k, v in enumerate(zs):
            zArr.SetValue(k, float(v))

        rg.SetXCoordinates(xArr)
        rg.SetYCoordinates(yArr)
        rg.SetZCoordinates(zArr)

        # Copy scalars from image data to rectilinear grid point data
        scalars = img.GetPointData().GetScalars()
        if scalars is None:
            raise ValueError("CT image data has no point scalars")
        if scalars.GetNumberOfTuples() != nx * ny * nz:
            raise ValueError("Scalar tuple count does not match volume dimensions")

        newScalars = self.reorderedPaddedScalars(img, flipX, flipY, flipZ)

        rg.GetPointData().SetScalars(newScalars)

        # Write legacy rectilinear grid
        w = vtk.vtkRectilinearGridWriter()
        w.SetFileName(outPath)
        w.SetInputData(rg)
        w.SetFileTypeToASCII()
        w.Write()

        # Add cell data field to file to satisfy py_bonemat_abaqus requirements
        path = Path(outPath)
        lines = path.read_text(encoding="utf-8").splitlines(True)
        nCells = (nx + dimPad - 1) * (ny + dimPad - 1) * (nz + dimPad - 1)
        # Find POINT_DATA line and insert CELL_DATA before it
        for i, line in enumerate(lines):
            if line.strip().startswith("POINT_DATA"):
                lines.insert(i, f"CELL_DATA {nCells}\n")
                break

        path.write_text("".join(lines), encoding="utf-8")
        

    def process(self, inputCT, inputMesh, outputMesh, algorithm):
        """
        Assign material properties to output volumetric mesh from input CT data
        """
        if not inputMesh.GetUnstructuredGrid():
            slicer.util.errorDisplay('Input mesh must be volumetric, not a surface')
            return
        
        configurePyBonematImports(__file__)

        from py_bonemat_abaqus.run import run as pyBonematAbaqusRun

        with tempfile.TemporaryDirectory(prefix='slicer_tmp_') as tmpdir:
            ctPath = os.path.join(tmpdir, 'ct.vtk')
            paramsPath = os.path.join(tmpdir, 'params.txt')
            meshPath = os.path.join(tmpdir, 'mesh.vtk')
            abaqusMeshPath = os.path.join(tmpdir, 'abaqus_mesh.inp')
            mappedAbaqusMeshPath = os.path.join(tmpdir, 'abaqus_meshMAT.inp')
            mappedMeshPath = os.path.join(tmpdir, 'mapped_mesh.vtk')

            ugridWriter = vtk.vtkUnstructuredGridWriter()
            ugridWriter.SetFileName(meshPath)
            ugridWriter.SetInputData(inputMesh.GetUnstructuredGrid())
            ugridWriter.SetFileTypeToASCII()
            ugridWriter.Write()

            preAbaqusMesh = meshio.read(meshPath)
            preAbaqusMesh.write(abaqusMeshPath)

            self.adjustAbaqusInput(abaqusMeshPath)

            self.writeVolumeAsRectilinearGrid(inputCT, ctPath)

            paraNode = self.getParameterNode()
            with open(paramsPath, 'w') as params:
                params.writelines([
                    'integration = ' + algorithm + '\n',
                    'gapValue = ' + str(paraNode.gapValue) + '\n',
                    'groupingDensity = max\n',
                    'intSteps = 4\n',
                    'rhoQCTa = ' + str(paraNode.ctDensityIntercept) + '\n',
                    'rhoQCTb = ' + str(paraNode.ctDensitySlope) + '\n',
                    'calibrationCorrect = True\n',
                    'numCTparam = single\n',
                    'rhoAsha1 = ' + str(paraNode.ashDensityOffset / (paraNode.ashDensityScale * paraNode.apparentDensityDivisor)) + '\n',
                    'rhoAshb1 =' + str(1 / (paraNode.ashDensityScale * paraNode.apparentDensityDivisor)) + '\n',
                    'numEparam = single\n',
                    'Ea1 = 0\n',
                    'Eb1 = ' + str(paraNode.modulusScale) + '\n',
                    'Ec1 = ' + str(paraNode.modulusExponent) + '\n',
                    'minVal = ' + str(paraNode.minModulus) + '\n',
                    'poisson = ' + str(paraNode.poissonValue)
                ])

            pyBonematAbaqusRun(paramsPath, ctPath, abaqusMeshPath)

            mappedAbaqusMesh = meshio.read(mappedAbaqusMeshPath)
            mappedAbaqusMesh.write(mappedMeshPath)

            # read lines to manually assign modulus values
            with open(mappedAbaqusMeshPath, 'r') as f:
                lines = f.readlines()

            ugridReader = vtk.vtkUnstructuredGridReader()
            ugridReader.SetFileName(mappedMeshPath)
            ugridReader.Update()
            ugrid = ugridReader.GetOutput()

        numCells = ugrid.GetNumberOfCells()
        moduli = vtk.vtkDoubleArray()
        moduli.SetName('YoungsModulus')
        moduli.SetNumberOfComponents(1)
        moduli.SetNumberOfTuples(numCells)

        modLookup = []
        i = 0
        while i < len(lines):
            if not lines[i].startswith('*Material'):
                i += 1
                continue

            modLine = lines[i+2]
            mod = float(modLine.strip().split(',')[0])
            if np.isnan(mod):
                mod = 15000
            modLookup.append(mod)
            i += 3

        modulusValues = [0] * numCells
        i = 0
        while i < len(lines):
            if not lines[i].startswith('*Elset'):
                i += 1
                continue

            j = i + 1
            while not lines[j].startswith('*'):
                j += 1
            
            elementLines = lines[i+1:j]
            elemIds = []
            for line in elementLines:
                elemIds.extend(int(x)-1 for x in line.replace("\n", ",").split(",") if x.strip())

            lookup = int(lines[i].strip().split('_')[-1]) - 1
            mod = modLookup[lookup]
            for id in elemIds:
                modulusValues[id] = mod

            i = j

        for cellId in range(numCells):
            moduli.SetValue(cellId, modulusValues[cellId])

        cellData = ugrid.GetCellData()
        if cellData.GetAbstractArray('YoungsModulus') is not None:
            cellData.RemoveArray('YoungsModulus')
        
        cellData.AddArray(moduli)
        cellData.SetScalars(moduli)

        outputMesh.SetAndObserveMesh(ugrid)

        self.displayOutputMesh(outputMesh)


#
# BoneMatTest
#


# class BoneMatTest(ScriptedLoadableModuleTest):
#     """
#     This is the test case for your scripted module.
#     Uses ScriptedLoadableModuleTest base class, available at:
#     https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
#     """

#     def setUp(self):
#         """Do whatever is needed to reset the state - typically a scene clear will be enough."""
#         slicer.mrmlScene.Clear()

#     def runTest(self):
#         """Run as few or as many tests as needed here."""
#         self.setUp()
#         self.test_MyFirstModule1()

#     def test_MyFirstModule1(self):
#         """Ideally you should have several levels of tests.  At the lowest level
#         tests should exercise the functionality of the logic with different inputs
#         (both valid and invalid).  At higher levels your tests should emulate the
#         way the user would interact with your code and confirm that it still works
#         the way you intended.
#         One of the most important features of the tests is that it should alert other
#         developers when their changes will have an impact on the behavior of your
#         module.  For example, if a developer removes a feature that you depend on,
#         your test should break so they know that the feature is needed.
#         """

#         self.delayDisplay("Starting the test")

#         # Get/create input data

#         import SampleData

#         registerSampleData()
#         inputVolume = SampleData.downloadSample("MyFirstModule1")
#         self.delayDisplay("Loaded test data set")

#         inputScalarRange = inputVolume.GetImageData().GetScalarRange()
#         self.assertEqual(inputScalarRange[0], 0)
#         self.assertEqual(inputScalarRange[1], 695)

#         outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
#         threshold = 100

#         # Test the module logic

#         logic = BoneMatLogic()

#         # Test algorithm with non-inverted threshold
#         logic.process(inputVolume, outputVolume, threshold, True)
#         outputScalarRange = outputVolume.GetImageData().GetScalarRange()
#         self.assertEqual(outputScalarRange[0], inputScalarRange[0])
#         self.assertEqual(outputScalarRange[1], threshold)

#         # Test algorithm with inverted threshold
#         logic.process(inputVolume, outputVolume, threshold, False)
#         outputScalarRange = outputVolume.GetImageData().GetScalarRange()
#         self.assertEqual(outputScalarRange[0], inputScalarRange[0])
#         self.assertEqual(outputScalarRange[1], inputScalarRange[1])

#         self.delayDisplay("Test passed")
