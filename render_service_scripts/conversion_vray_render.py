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