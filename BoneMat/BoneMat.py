import os
import sys
import math
import time
from typing import Optional
from __main__ import qt

import vtk
from vtk.util import numpy_support
from vtkmodules.vtkFiltersVerdict import vtkMeshQuality
import numpy as np
import json
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

configurePyBonematImports(__file__)

from py_bonemat_abaqus.data_import import _checkParamInformation, _create_part
from py_bonemat_abaqus.classes import part, vtk_data
from py_bonemat_abaqus.calc import _check_elements_in_CT, _assign_mat_props, _limit_num_materials
    
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
    numIntegrationSteps: int
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
        self._plots = {}
        self._meshStats = {}

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

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

        # setup various UI elements
        self.setupConnections()
        self.setupDropdowns()
        self.setupPhantomTable()
        self.setupProgressLog()

        # setting default values
        self.setBoneDensityPresetValues()
        self.setDefaultValues()

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

    def setupConnections(self) -> None:
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

    def setupDropdowns(self) -> None:
        # Setup input mesh statistics options
        self.ui.inputMeshStatSelector.addItem('Element volume', 'vol')
        self.ui.inputMeshStatSelector.addItem('Tetrahedron quality', 'tet_quality')
        self.ui.inputMeshStatSelector.addItem('Maximum element edge length', 'max_edge')
        self.ui.inputMeshStatSelector.addItem('Minimum element edge length', 'min_edge')
        self.ui.inputMeshStatSelector.setCurrentIndex(0)

        # Setup download formats
        self.ui.downloadFormatSelector.addItem('VTK', '.vtk')
        self.ui.downloadFormatSelector.addItem('FEBio (.feb)', '.feb')
        self.ui.downloadFormatSelector.addItem('Abaqus (.inp)', '.inp')
        self.ui.downloadFormatSelector.addItem('Ansys (.cdb)', '.cdb')
        self.ui.downloadFormatSelector.setCurrentIndex(0)

        # Setup algorithm choices
        self.ui.algoSelector.addItem('HU averaging (Bonemat v1)', None)
        self.ui.algoSelector.addItem('HU integration (Bonemat v2)', 'HU')
        self.ui.algoSelector.addItem('E integration (Bonemat v3)', 'E')
        self.ui.algoSelector.setCurrentIndex(2)

    def setupPhantomTable(self) -> None:
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

    def setupProgressLog(self) -> None:
        self.ui.progressBar.hide()

        log = self.ui.processLog
        log.setFixedHeight(80)
        log.setReadOnly(True)

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

    def setDefaultValues(self) -> None:
        # Default values for some options
        with slicer.util.NodeModify(self._parameterNode):
            self._parameterNode.meshNodes = '0'
            self._parameterNode.meshElements = '0'
            self._parameterNode.meshMinStat = '0'
            self._parameterNode.meshMaxStat = '0'
            self._parameterNode.meshAvgStat = '0'

            self._parameterNode.minModulus = 10
            self._parameterNode.numIntegrationSteps = 3
            self._parameterNode.poissonValue = 0.35
            self._parameterNode.gapValue = 200
            self._parameterNode.ctPadDepth = 1
            self._parameterNode.ctPadValue = -1000

    def _checkCanApply(self, caller=None, event=None) -> None:
        if self._parameterNode and self._parameterNode.inputCT and self._parameterNode.inputVolMesh and self._parameterNode.outputVolMesh:
            self.ui.applyButton.toolTip = _("Commence material property assignment")
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = _("Select input CT, input mesh and output mesh")
            self.ui.applyButton.enabled = False

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
        self.ui.processLog.clear()
        self.appendLog('Calculating input mesh statistics...')

        mesh = self._parameterNode.inputVolMesh
        if mesh is None:
            self.appendLog('ERROR: no input mesh selected.')
            return
        
        self.ui.calcMeshStatsButton.enabled = False
        self.ui.calcMeshStatsButton.text = 'Loading...'
        slicer.app.processEvents()

        numNodes, numCells, stats = self.logic.computeMeshStats(mesh, self._meshStats)

        self._parameterNode.meshNodes = str(numNodes)
        self._parameterNode.meshElements = str(numCells)

        self.ui.calcMeshStatsButton.enabled = True
        self.ui.calcMeshStatsButton.text = 'Calculate'

        self.createMeshStatsPlots(stats)

        self.onMeshStatSelection()

        self.appendLog('Mesh statistics calculated.')

    def createMeshStatsPlots(self, stats) -> None:
        volumeTable = self.createMeshStatTable(stats['volume'])
        tetQualityTable = self.createMeshStatTable(stats['tetQuality'])
        minEdgeTable = self.createMeshStatTable(stats['minEdge'])
        maxEdgeTable = self.createMeshStatTable(stats['maxEdge'])

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
        try:
            self.ui.processLog.clear()
            self.appendLog('Starting material assignment procedure.')

            start = time.time()
            self.logic.process(self._parameterNode.inputCT,
                                self._parameterNode.inputVolMesh,
                                self._parameterNode.outputVolMesh,
                                self.ui.algoSelector.currentData,
                                self.ui.progressBar)

            self.appendLog(f'Material assignment complete.\nElapsed time (seconds): {time.time() - start}')
        except Exception as e:
            self.appendLog(f"ERROR: {e}")

    def onDownloadButton(self) -> None:
        outputModel = self._parameterNode.outputVolMesh
        if not outputModel:
            self.appendLog('ERROR: No output model available to export')
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

            self.logic.exportOutputMesh(downloadExt,
                                        filePath,
                                        outputModel.GetUnstructuredGrid(),
                                        self._parameterNode.poissonValue)
            
            self.appendLog(f"Mesh saved to: {filePath}")
        except Exception as e:
            self.appendLog(f"ERROR: Failed to save mesh: {e}")

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
        
        slope, intercept = self.logic.calcDensityVars(cellItems)

        self.ui.ctDensitySlopeSpinBox.value = slope
        self.ui.ctDensityInterceptSpinBox.value = intercept

    def appendLog(self, errMsg) -> None:
        log = self.ui.processLog
        log.appendPlainText(errMsg)

        scrollbar = log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum)

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

    def process(self, inputCT, inputMesh, outputMesh, algorithm, progressBar):
        """
        Assign material properties to output volumetric mesh from input CT data
        """
        ugrid = inputMesh.GetUnstructuredGrid()
        if not ugrid:
            raise Exception('Input mesh must be volumetric, not a surface')
        
        cellTypes = vtk.vtkCellTypes()
        ugrid.GetCellTypes(cellTypes)
        if cellTypes.GetNumberOfTypes() > 1:
            raise Exception('Input mesh must be homogenous (i.e. all elements are the same type)')
        if cellTypes.GetCellType(0) not in [vtk.VTK_TETRA, vtk.VTK_QUADRATIC_TETRA, vtk.VTK_WEDGE, vtk.VTK_HEXAHEDRON]:
            raise Exception('Input mesh elements must be linear tet, quadratic tet, linear wedge or linear hex elements')

        params = self.getParams(algorithm)
        meshPart = self.getMeshPart(ugrid)
        vtkCT = self.getVtkCTData(inputCT)

        progressBar.setValue(0)
        progressBar.show()

        _check_elements_in_CT(meshPart, vtkCT)
        mappedMeshPart = _assign_mat_props(meshPart, params, vtkCT, progressBar)
        mappedMeshPart.moduli = _limit_num_materials(mappedMeshPart.moduli, 
                                                      params['gapValue'], 
                                                      params['minVal'], 
                                                      params['groupingDensity'])

        numCells = ugrid.GetNumberOfCells()
        moduli = vtk.vtkDoubleArray()
        moduli.SetName('YoungsModulus')
        moduli.SetNumberOfComponents(1)
        moduli.SetNumberOfTuples(numCells)

        for cellId in range(numCells):
            moduli.SetValue(cellId, mappedMeshPart.moduli[cellId])

        progressBar.hide()

        cellData = ugrid.GetCellData()
        if cellData.GetAbstractArray('YoungsModulus') is not None:
            cellData.RemoveArray('YoungsModulus')
        
        cellData.AddArray(moduli)
        cellData.SetScalars(moduli)

        outputMesh.SetAndObserveMesh(ugrid)

        self.displayOutputMesh(outputMesh)

    def getParams(self, algorithm) -> dict:
        paraNode = self.getParameterNode()
        if paraNode.ashDensityScale == 0 or paraNode.apparentDensityDivisor == 0:
            raise Exception('All divisors in bone density formulation steps must be non-zero')
        
        params = {
            'integration': algorithm,
            'gapValue': float(paraNode.gapValue),
            'groupingDensity': 'max',
            'intSteps': paraNode.numIntegrationSteps,
            'rhoQCTa': paraNode.ctDensityIntercept,
            'rhoQCTb': paraNode.ctDensitySlope,
            'calibrationCorrect': True,
            'numCTparam': 'single',
            'rhoAsha1': paraNode.ashDensityOffset / (paraNode.ashDensityScale * paraNode.apparentDensityDivisor),
            'rhoAshb1': 1 / (paraNode.ashDensityScale * paraNode.apparentDensityDivisor),
            'numEparam': 'single',
            'Ea1': 0.0,
            'Eb1': paraNode.modulusScale,
            'Ec1': paraNode.modulusExponent,
            'minVal': paraNode.minModulus,
            'poisson': paraNode.poissonValue
        }
        _checkParamInformation(params)

        return params

    def getMeshPart(self, ugrid) -> part:
        points = []
        for i in range(ugrid.GetNumberOfPoints()):
            points.append(ugrid.GetPoint(i))

        cells = []
        # mesh was checked for homogeneity in 'process' 
        numPts = ugrid.GetCell(0).GetNumberOfPoints()
        for i in range(ugrid.GetNumberOfCells()):
            cell = ugrid.GetCell(i)
            pointIds = [cell.GetPointIds().GetId(j) for j in range(numPts)]
            cells.append([i] + pointIds)

        cellName = ''
        cellType = ''
        vtkCellType = ugrid.GetCell(0).GetCellType()
        if vtkCellType == vtk.VTK_TETRA:
            cellName = 'C3D4'
            cellType = 'linear_tet'
        elif vtkCellType == vtk.VTK_QUADRATIC_TETRA:
            cellName = 'C3D10'
            cellType = 'quad_tet'
        elif vtkCellType == vtk.VTK_WEDGE:
            cellName = 'C3D6'
            cellType = 'linear_wedge'
        elif vtkCellType == vtk.VTK_HEXAHEDRON:
            cellName = 'C3D8'
            cellType = 'linear_hex'

        return _create_part('input_mesh', cells, cellName, cellType, points)
    
    def getVtkCTData(self, volNode):
        img = volNode.GetImageData()
        if img is None:
            raise Exception("Volume node has no image data")
        
        padDepth = self.getParameterNode().ctPadDepth
        if padDepth < 0:
            raise Exception('CT padding voxel depth must be >= 0')

        nx, ny, nz = img.GetDimensions()

        ijkToRas = vtk.vtkMatrix4x4()
        volNode.GetIJKToRASMatrix(ijkToRas)

        self.checkAxisAligned(ijkToRas)

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
        leftXPadding = xs[0] - xDiff * np.arange(padDepth, 0, -1)
        rightXPadding = xs[nx - 1] + xDiff * np.arange(1, padDepth + 1)
        xs = np.concatenate((leftXPadding, xs, rightXPadding))

        yDiff = ys[1] - ys[0]
        leftYPadding = ys[0] - yDiff * np.arange(padDepth, 0, -1)
        rightYPadding = ys[ny - 1] + yDiff * np.arange(1, padDepth + 1)
        ys = np.concatenate((leftYPadding, ys, rightYPadding))

        zDiff = zs[1] - zs[0]
        leftZPadding = zs[0] - zDiff * np.arange(padDepth, 0, -1)
        rightZPadding = zs[nz - 1] + zDiff * np.arange(1, padDepth + 1)
        zs = np.concatenate((leftZPadding, zs, rightZPadding))
        
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

        # Copy scalars from image data to rectilinear grid point data
        scalars = img.GetPointData().GetScalars()
        if scalars is None:
            raise Exception("CT image data has no point scalars (i.e. HU data)")
        if scalars.GetNumberOfTuples() != nx * ny * nz:
            raise Exception("CT image data count does not match volume dimensions")

        newScalars = self.reorderedPaddedScalars(img, flipX, flipY, flipZ)

        return vtk_data(xs, ys, zs, newScalars)
    
    def checkAxisAligned(self, ijkToRas) -> None:
        direction = np.zeros((3, 3), dtype=float)
        for r in range(3):
            for c in range(3):
                direction[r, c] = ijkToRas.GetElement(r, c)

        # Remove spacing by normalizing each IJK axis vector.
        for c in range(3):
            norm = np.linalg.norm(direction[:, c])
            if norm == 0:
                raise Exception("CT image has an invalid IJK-to-RAS matrix")
            direction[:, c] /= norm

        absDirection = np.abs(direction)

        # Axis-aligned means each IJK axis points almost entirely along one RAS axis.
        offAxis = absDirection.copy()
        for c in range(3):
            offAxis[np.argmax(absDirection[:, c]), c] = 0

        if np.any(offAxis > 1e-4):
            raise Exception(
                "Input CT is obliquely oriented. Please resample/reformat it to an "
                "axis-aligned volume before running BoneMat."
            )
    
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

        return np.ascontiguousarray(paddedVol.reshape(-1))
    
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

    def computeMeshStats(self, mesh, meshStats) -> dict:
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

        meshStats["meshMinVol"] = np.min(volume)
        meshStats["meshMaxVol"] = np.max(volume)
        meshStats["meshAvgVol"] = np.mean(volume)

        meshStats["meshMinTetQual"] = np.min(tetQuality)
        meshStats["meshMaxTetQual"] = np.max(tetQuality)
        meshStats["meshAvgTetQual"] = np.mean(tetQuality)

        meshStats["meshMinMinEdge"] = np.min(minEdge)
        meshStats["meshMaxMinEdge"] = np.max(minEdge)
        meshStats["meshAvgMinEdge"] = np.mean(minEdge)

        meshStats["meshMinMaxEdge"] = np.min(maxEdge)
        meshStats["meshMaxMaxEdge"] = np.max(maxEdge)
        meshStats["meshAvgMaxEdge"] = np.mean(maxEdge)

        stats = {
            'volume': volume,
            'tetQuality': tetQuality,
            'minEdge': minEdge,
            'maxEdge': maxEdge
        }
        return ugrid.GetNumberOfPoints(), ugrid.GetNumberOfCells(), stats
    
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
    
    def exportOutputMesh(self, ext, filePath, ugrid, poisson) -> None:
        if ext == '.vtk':
            ugridWriter = vtk.vtkUnstructuredGridWriter()
            ugridWriter.SetFileName(filePath)
            ugridWriter.SetInputData(ugrid)
            ugridWriter.SetFileTypeToASCII()
            ugridWriter.Write()
        elif ext == '.inp':
            self.exportAbaqusMesh(ugrid, filePath, poisson)
        elif ext == '.feb':
            self.exportFebioMesh(ugrid, filePath, poisson)
        elif ext == '.cdb':
            self.exportAnsysMesh(ugrid, filePath, poisson)

    def exportAbaqusMesh(self, ugrid, filePath, poisson) -> None:
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
            raise Exception('Output model has no attached Young\'s Modulus data')
        
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
                f'{mod}, {poisson}\n'
            ])

        with open(filePath, 'w') as f:
            f.writelines(lines)

    def exportFebioMesh(self, ugrid, filePath, poisson) -> None:
        lines = [
            '<?xml version="1.0" encoding="ISO-8859-1"?>\n',
            '<febio_spec version="4.0">\n'
        ]

        # Assume we'll be doing a structural mechanics analysis
        lines.append('\t<Module type="solid"/>\n')

        vtkModuli = ugrid.GetCellData().GetAbstractArray('YoungsModulus')
        if vtkModuli is None:
            raise Exception('Output model has no attached Young\'s Modulus data')
        
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
            f'\t\t\t<v>{poisson}</v>\n',
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

    def exportAnsysMesh(self, ugrid, filePath, poisson) -> None:
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
            raise Exception('Output model has no attached Young\'s Modulus data')

        moduli = numpy_support.vtk_to_numpy(vtkModuli)
        modSet = np.sort(np.unique(moduli))
        indexToMod = {i+1: value for i, value in enumerate(modSet)}.items()

        for matNum, mod in indexToMod:
            lines.extend([
                f'MP,EX,{matNum},{mod}\n',
                f'MP,NUXY,{matNum},{poisson}\n\n'
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
    
    def calcDensityVars(self, cellItems) -> tuple:
        nums = [float(x.text()) for x in cellItems]
        slope = (nums[1] - nums[3]) / (nums[0] - nums[2])
        intercept = nums[1] - slope * nums[0]
        return slope / 1000, intercept / 1000

