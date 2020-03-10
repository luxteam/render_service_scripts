import os
import maya.cmds as cmds
import maya.mel as mel
import datetime
import json


def resolveFilePath():
    unresolved_files = cmds.filePathEditor(query=True, listFiles="", unresolved=True, attributeOnly=True)
    if unresolved_files:
        try:
            new_path = "{project}";
            for item in unresolved_files:
                cmds.filePathEditor(item, repath=new_path, recursive=True, replaceAll=True)
        except:
            pass


def rpr_render():

    if {max_samples}:
        cmds.setAttr("RadeonProRenderGlobals.completionCriteriaIterations", {max_samples})
    if {min_samples}:
        cmds.setAttr("RadeonProRenderGlobals.completionCriteriaMinIterations", {min_samples})
    if {noise_threshold}:
        cmds.setAttr("RadeonProRenderGlobals.adaptiveThreshold", {noise_threshold})
    cmds.setAttr("RadeonProRenderGlobals.completionCriteriaMinutes", 30)

    if {width}:
        cmds.setAttr("defaultResolution.width", {width})
    if {height}:
        cmds.setAttr("defaultResolution.height", {height})

    cmds.optionVar(rm="RPR_DevicesSelected")
    cmds.optionVar(iva=("RPR_DevicesSelected", 1))

    # scene name
    split_name = cmds.file(q=True, sn=True, shn=True).split('.')
    scenename = '.'.join(split_name[0:-1])

    cmds.setAttr("defaultRenderGlobals.imageFilePrefix", "{res_path}/Output/" + scenename, type="string")


def main():
    resolveFilePath()
    rpr_render()

    # results json
    report = {{}}
    report['width'] = cmds.getAttr("defaultResolution.width")
    report['height'] = cmds.getAttr("defaultResolution.height")
    report['min_samples'] = cmds.getAttr("RadeonProRenderGlobals.completionCriteriaMinIterations")
    report['max_samples'] = cmds.getAttr("RadeonProRenderGlobals.completionCriteriaIterations")
    report['noise_threshold'] = cmds.getAttr("RadeonProRenderGlobals.adaptiveThreshold")
    with open(os.path.join(".", "render_info.json"), 'w') as f:
        json.dump(report, f, indent=4)