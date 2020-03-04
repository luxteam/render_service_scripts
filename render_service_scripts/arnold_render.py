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


def main():

	mel.eval("setProject(\"{project}\")")

	# scene name
	split_name = cmds.file(q=True, sn=True, shn=True).split('.')
	scenename = '.'.join(split_name[0:-1])

	cmds.setAttr("defaultRenderGlobals.imageFilePrefix", "{res_path}/Output/" + scenename, type="string")

	resolveFilePath()

	if {max_samples}:
		pass
	if {min_samples}:
		pass
	if {noise_threshold}:
		pass

	if {width}:
		cmds.setAttr("defaultResolution.width", {width})
	if {height}:
		cmds.setAttr("defaultResolution.height", {height})

	# results json
	report = {{}}
	report['width'] = cmds.getAttr("defaultResolution.width")
	report['height'] = cmds.getAttr("defaultResolution.height")
	with open(os.path.join(".", "render_info.json"), 'w') as f:
		json.dump(report, f, indent=4)
