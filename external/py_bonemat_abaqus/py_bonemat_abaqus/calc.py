#!/usr/bin/python
#
# py_bonemat_abaqus - calc
# ========================
#
# Created by Elise Pegg, University of Bath

__all__ = ['calc_mat_props']

#-------------------------------------------------------------------------------
# Import modules
#-------------------------------------------------------------------------------
import numpy as np
from numpy import mean, arange, digitize, array
from copy import deepcopy
from py_bonemat_abaqus.classes import vtk_data
import sys
from bisect import bisect_right
from operator import itemgetter

#-------------------------------------------------------------------------------
# Functions for calculating material data
#-------------------------------------------------------------------------------
def calc_mat_props(part, param, vtk):
    """ Find material properties of each part """
    
    # first check that elements are all within CT volume
    _check_elements_in_CT(part, vtk)

    # calculate the material properties
    part = _assign_mat_props(part, param, vtk)

    # group modulus values
    part.moduli = _limit_num_materials(part.moduli, 
                                        param['gapValue'], 
                                        param['minVal'], 
                                        param['groupingDensity'])

    return part
    
def _assign_mat_props(part, param, vtk, progressBar):
    """ Find material properties of each element """
    
    # define equations from parameters file
    rhoQCT_equ, rhoAsh_equ, modulus_equ = _define_equations(param)

    progressIndexes = np.linspace(0, len(part.elements) - 1, 100, dtype=int)
    moduli = []

    # if V1
    if param['integration'] == None:
        # check that the elements are linear tets
        if part.ele_type != 'linear_tet':
            raise IOError('Version 1 will only work with linear tets, modify parameters file')
            
        for i, e in enumerate(part.elements):
            # update progress bar
            matches = np.where(progressIndexes == i)[0]
            if len(matches) > 0:
                progressBar.setValue(matches[-1] + 1)

            # find voxels
            voxels = vtk.get_voxels(e)
            
            # calculate the mean intensity for the element
            mean_hu = mean([vtk.lookup[i] for i in voxels])
            
            # apply equations to calculate the modulus
            modulus = _apply_equations(mean_hu, rhoQCT_equ, rhoAsh_equ, modulus_equ)
            moduli.append(modulus)

    # if V2
    if param['integration'] == 'HU':
        for i, e in enumerate(part.elements):
            # update progress bar
            matches = np.where(progressIndexes == i)[0]
            if len(matches) > 0:
                progressBar.setValue(matches[-1] + 1)

            # find scalar through integration       
            hu = e.integral(param['intSteps'], vtk)
                            
            # calculate the modulus value
            modulus = _apply_equations(hu, rhoQCT_equ, rhoAsh_equ, modulus_equ)
            moduli.append(modulus)

    # if V3
    if param['integration'] == 'E':
        for i, e in enumerate(part.elements):
            # update progress bar
            matches = np.where(progressIndexes == i)[0]
            if len(matches) > 0:
                progressBar.setValue(matches[-1] + 1)

            # find modulus for the element
            modulus = e.integral(param['intSteps'], 
                                  vtk, 
                                  rhoQCT_equ, 
                                  rhoAsh_equ, 
                                  modulus_equ)
            moduli.append(modulus)

    # save
    part = _save_modulus(part, moduli)

    return part

def _apply_equations(hu, rhoQCT, rhoAsh, modulus):
    """ Uses the three defined equations to calculate the modulus """

    return modulus(rhoAsh(rhoQCT(hu)))    

def _save_modulus(part, modulus):
    """ Save modulus data in part class """
    
    part.moduli = modulus

    return part
    
def _check_elements_in_CT(part, vtk):
    node_data = array(_get_node_data(part))
    i,x,y,z = node_data.T
    if min(x) < min(vtk.x):
        n_indx = i[x.tolist().index(min(x))]
        raise ValueError("Error: Node " + repr(int(n_indx)) + " has an x-coordinate of: " + repr(min(x)) + " which is outside the CT volume\n"
                            "Dataset minimum x value is: " + repr(min(vtk.x)))
    elif min(y) < min(vtk.y):
        n_indx = i[y.tolist().index(min(y))]
        raise ValueError("Error: Node " + repr(int(n_indx)) + " has a y-coordinate of: " + repr(min(y)) + " which is outside the CT volume\n"
                            "Dataset minimum y value is: " + repr(min(vtk.y)))
    elif min(z) < min(vtk.z):
        n_indx = i[z.tolist().index(min(z))]
        raise ValueError("Error: Node " + repr(int(n_indx)) + " has a z-coordinate of: " + repr(min(z)) + " which is outside the CT volume\n"
                            "Dataset minimum z value is: " + repr(min(vtk.z)))
    elif max(x) > max(vtk.x):
        n_indx = i[x.tolist().index(max(x))]
        raise ValueError("Error: Node " + repr(int(n_indx)) + " has an x-coordinate of: " + repr(max(x)) + " which is outside the CT volume\n"
                            "Dataset maximum x value is: " + repr(max(vtk.x)))
    elif max(y) > max(vtk.y):
        n_indx = i[y.tolist().index(max(y))]
        raise ValueError("Error: Node " + repr(int(n_indx)) + " has a y-coordinate of: " + repr(max(y)) + " which is outside the CT volume\n"
                            "Dataset maximum y value is: " + repr(max(vtk.y)))
    elif max(z) > max(vtk.z):
        n_indx = i[z.tolist().index(max(z))]
        raise ValueError("Error: Node " + repr(int(n_indx)) + " has a z-coordinate of: " + repr(max(z)) + " which is outside the CT volume\n"
                            "Dataset maximum z value is: " + repr(max(vtk.z)))
                             
def _get_node_data(part):
    """ Identifies node data using part class """

    # join node index with co-ordinate data
    nodes = {}
    for e in part.elements:
        for n in range(len(e.nodes)):
            nodes[e.nodes[n]] = e.pts[n]

    # create array of data
    node_data = []
    for n in list(nodes.keys()):
        node_data.append([int(n), nodes[n][0], nodes[n][1], nodes[n][2]])

    return sorted(node_data)                             

#-------------------------------------------------------------------------------
# Functions for calculating modulus values
#-------------------------------------------------------------------------------
def _define_equations(param):
    """ From parameters inputs define equation lambda functions """

    # define calibration calculation
    def rhoQCT(HU):
        res = param['rhoQCTa'] + (param['rhoQCTb'] * HU)
        if res < 0:
            return 0.000001
        else:
            return res
    
    # define calibration correction calculation
    if param['calibrationCorrect'] == False:
        rhoAsh = lambda Q: Q
    elif param['calibrationCorrect'] == True:
        if param['numCTparam'] == 'single':
            def rhoAsh(Q):
                res = param['rhoAsha1'] + (param['rhoAshb1'] * Q)
                if res < 0:
                    return 0.000001
                else:
                    return res
        elif param['numCTparam'] == 'triple':
            def rhoAsh(Q):                
                if Q < param['rhoThresh1']:
                    res = param['rhoAsha1'] + (param['rhoAshb1'] * Q)
                elif (Q >= param['rhoThresh1']) & (Q <= param['rhoThresh2']):
                    res = param['rhoAsha2'] + (param['rhoAshb2'] * Q)
                else:
                    res = param['rhoAsha3'] + (param['rhoAshb3'] * Q)
                if res < 0:
                    return 0.000001
                else:
                    return res
        else:
            IOError("Error: " + param['numCTparam'] + " is not a valid input for numCTparam.  \
                     Must be 'single' or 'triple'")
    
    # define modulus calculation
    if param['numEparam'] == 'single':
        def modulus(Ash):
            res = param['Ea1'] + (param['Eb1'] * (Ash ** param['Ec1']))
            if res < 0:
                return 0.000001
            else:
                return res
    elif param['numEparam'] == 'triple':
        def modulus(Ash):
            if Ash < param['Ethresh1']:
                res = param['Ea1'] + (param['Eb1'] * (Ash ** param['Ec1']))
            elif (Ash >= param['Ethresh1']) & (Ash <= param['Ethresh2']):
                res = param['Ea2'] + (param['Eb2'] * (Ash ** param['Ec2']))
            elif Ash > param['Ethresh2']:
                res = param['Ea3'] + (param['Eb3'] * (Ash ** param['Ec3']))
            else:
                raise ValueError("Error: modulus for density value: " + repr(Ash) + " cannot be calculated")
            if res < 0:
                return 0.000001
            else:
                return res
    else:
        IOError("Error: " + param['numEparam'] + " is not a valid input for numCTparam.  Must be 'single' or 'triple'")       

    return rhoQCT, rhoAsh, modulus

def _identify_voxels_in_tets(part, vtk):
    """ Iterate through each element and identifies voxels within """
    
    voxels = []
    for e in part.elements:
        voxels.append(vtk.get_voxels(e))
        
    return voxels     
    
#-------------------------------------------------------------------------------
# Functions for grouping modulus values
#-------------------------------------------------------------------------------    
def _refine_materials(parts, param):
    """ Group the materials into bins separated by the gapValue parameter """

    # limit the moduli values for each part
    for p in range(len(parts)):
        if parts[p].ignore != True:
            parts[p].moduli = _limit_num_materials(parts[p].moduli, 
                                                   param['gapValue'], 
                                                   param['minVal'], 
                                                   param['groupingDensity'])

    return parts
    
def _get_all_modulus_values(parts):
    """ Create list of all modulus values for all parts in model """
    
    moduli = []
    for p in parts:
        if p.ignore != True:
            moduli.extend(p.moduli)

    return moduli    
    
def _get_mod_intervals(moduli, max_materials):
    """ Find the refined moduli values """

    min_mod = float(min(moduli))
    max_mod = float(max(moduli))
    if len(set(moduli)) < max_materials:
        mod_interval = 0.0
    else:
        mod_interval = (max_mod - min_mod) / float(max_materials)

    return mod_interval
    
def _limit_num_materials(moduli, gapValue, minVal, groupingDensity):
    """ Groups the moduli into bins and calculates the max/mean for each """
    
    if gapValue == 0:
        return moduli
    elif gapValue == 1:
        return np.ceil(moduli)
    else:
	    # calculate the modulus values
        indices, sorted_moduli = list(zip(*sorted(enumerate(moduli), key=itemgetter(1))))
        new_moduli = [minVal] * len(moduli)

        end = len(moduli)
        while end > 0:
            maxVal = sorted_moduli[end - 1]
            b = bisect_right(sorted_moduli, maxVal - gapValue, 0, end)
            if groupingDensity == 'max':
                val = maxVal
            elif groupingDensity =='mean':
                val = sum(sorted_moduli[b:end]) / (end - b)
            else:
                raise IOError("Error: groupingDensity should be 'max' or 'mean' in parameters file")
            if val < minVal:
                val = minVal
            for i in indices[b:end]:
                new_moduli[i] = val

            end = b                       
                        
        return new_moduli
        
