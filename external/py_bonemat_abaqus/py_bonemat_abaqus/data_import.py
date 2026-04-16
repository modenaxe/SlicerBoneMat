#!/usr/bin/python
#
# py_bonemat_abaqus - data import
# ===============================
#
# Created by Elise Pegg, University of Bath

__all__ = ['import_parameters','import_mesh','import_ct_data']
           
#-------------------------------------------------------------------------------
# Import modules
#-------------------------------------------------------------------------------
from py_bonemat_abaqus.classes import linear_tet, quad_tet, linear_wedge, linear_hex
from py_bonemat_abaqus.classes import part

#-------------------------------------------------------------------------------
# Functions for importing parameters
#------------------------------------------------------------------------------
    
def _checkParamInformation(param):
    """ Iterates through parameters file to check contains all required information """
    
    # assign default parameters if not defined
    if 'integration' not in list(param.keys()):
        param['integration'] = 'E'
        print("        Note: 'integration' parameter not defined. Assigning to default, E (Equivalent to Bonemat V3)")
        
    if 'groupingDensity' not in list(param.keys()):
        param['groupingDensity'] = 'mean'
        print("        Note: 'groupingDensity' parameter not defined. Assigning to default, 'mean'")
    
    # check for essential information
    _checkNecessaryParam(param, ['integration', 'gapValue','groupingDensity','intSteps','rhoQCTa','rhoQCTb',
                                'calibrationCorrect','minVal','poisson','numEparam'],)
    
    # if appropriate, check for calibration information
    if param['calibrationCorrect'] == True:
        _checkNecessaryParam(param, ['numCTparam'])
        if param['numCTparam'] == 'single':
            _checkNecessaryParam(param, ['rhoAsha1','rhoAshb1'])
        elif param['numCTparam'] == 'triple':
            _checkNecessaryParam(param, ['rhoThresh1','rhoThresh2','rhoAsha1','rhoAshb1', 'rhoAsha2','rhoAshb2',
                                        'rhoAsha3','rhoAshb3'])
        else:
            raise IOError("Error: " + param['numCTparam'] + " is not a valid input for numCTparam.  Must be 'single' or 'triple'")  
    
    # if appropriate check for modulus calculation information
    if param['numEparam'] == 'single':
        _checkNecessaryParam(param, ['Ea1','Eb1','Ec1'])
    elif param['numEparam'] == 'triple':
        _checkNecessaryParam(param, ['Ea1','Eb1','Ec1', 'Ea2','Eb2','Ec2','Ea3','Eb3','Ec3'])
    else:
        raise IOError("Error: " + param['numEparam'] + " is not a valid input for numCTparam. Must be 'single' or 'triple'")  
        
    # check all values which need to be are numerical
    _checkNumericalParam(param)       
    
    
def _checkNumericalParam(param):    
    """ Checks parameters fields which need to be numerical are """
    
    # check ints
    if param['intSteps'] != int(param['intSteps']):
        raise IOError("Error: intSteps parameter must be an integer")
    
    # check floats
    floats = ['gapValue','rhoQCTa','rhoQCTb','rhoThresh1','rhoThresh2','rhoAsha1','rhoAshb1','rhoAsha2','rhoAshb2','rhoAsha3',
              'rhoAshb3', 'Ethresh1','Ethresh2','Ea1','Eb1','Ec1','Ea2','Eb2','Ec2','Ea3','Eb3','Ec3','minVal','poisson']
    for f in floats:
        if f in list(param.keys()):
            if type(param[f]) != float:
                raise IOError("Error: " + param[f] + " must be a numerical value")
    
def _checkNecessaryParam(param, fields):
    for f in fields:
        if f not in list(param.keys()):
            raise IOError("Error: " + f + " is not defined in parameters file")
        
#-------------------------------------------------------------------------------
# Functions for importing mesh data
#-------------------------------------------------------------------------------

def _create_part(name, elements, elename, eletype, nodes, transform=[[0.,0.,0]], ignore=False):
    """ Creates part class from input data """
    
    # create the part
    new_part = part(name, elename, eletype, transform, ignore)

    # add elements to part
    for e in elements:
        pts = [nodes[n] for n in e[1:]]
        # FIX TO UPGRADE TO PYTHON 3:
        # it is bad practice to use exec or eval.
        # replaced with choice of elements.
        # needs updates if additional elements are added
        # exec('ele = ' + eletype + '(int(e[0]), pts, e[1:])')
        # python 3 version of original code
        # ele = eval(eletype + '(int(e[0]), pts, e[1:])')
        if eletype == 'linear_tet':
            ele = linear_tet(int(e[0]), pts, e[1:])
        if eletype == 'quad_tet':
            ele = quad_tet(int(e[0]), pts, e[1:])
        if eletype == 'linear_wedge':
            ele = linear_wedge(int(e[0]), pts, e[1:])
        if eletype == 'linear_hex':
            ele = linear_hex(int(e[0]), pts, e[1:])
        ################################

        new_part.add_element(ele)
        
    return new_part
