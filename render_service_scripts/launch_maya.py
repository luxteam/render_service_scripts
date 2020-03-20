import argparse
import subprocess
import psutil
import json
import ctypes
import requests
import glob
import os
import logging
import datetime
import threading
from time import sleep
from file_read_backwards import FileReadBackwards
from render_service_scripts.unpack import unpack_scene
from pathlib import Path
from render_service_scripts.utils import Util


# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'Output'


def get_windows_titles():
	EnumWindows = ctypes.windll.user32.EnumWindows
	EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
	GetWindowText = ctypes.windll.user32.GetWindowTextW
	GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
	IsWindowVisible = ctypes.windll.user32.IsWindowVisible

	titles = []

	def foreach_window(hwnd, lParam):
		if IsWindowVisible(hwnd):
			length = GetWindowTextLength(hwnd)
			buff = ctypes.create_unicode_buffer(length + 1)
			GetWindowText(hwnd, buff, length + 1)
			titles.append(buff.value)
		return True

	EnumWindows(EnumWindowsProc(foreach_window), 0)

	return titles


def start_monitor_render_thread(args, util):
	post_data = {'status': 'Rendering', 'id': args.id}
	util.send_status(post_data)
	thread = threading.currentThread()
	delay = 10
	log_file = os.path.join(OUTPUT_DIR, "batch_render_log.txt")
	all_frames = int(args.endFrame) - int(args.startFrame) + 1
	while getattr(thread, "run", True):
		try :
			with FileReadBackwards(log_file, encoding="utf-8") as file:
				for line in file:
					if "Percentage of rendering done" in line:
						frame_number = int(line.split("(", 1)[1].split(",", 1)[0].split(" ", 1)[1])
						current_percentage = int(line.rsplit(":", 1)[1].strip().split(" ", 1)[0])
						rendered = ((frame_number - int(args.startFrame)) * 100 + current_percentage) / (all_frames * 100) * 100
						status = 'Rendering ( ' + str(round(rendered, 2)) + '% )'
						post_data = {'status': status, 'id': args.id}
						util.send_status(post_data)
						break
		except FileNotFoundError:
			pass
		sleep(10)


def main():
	args = Util.get_render_args('--batchRender')

	# create utils object
	util = Util(ip=args.django_ip, logger=logger, args=args)

	# create output folder for images and logs
	util.create_dir(OUTPUT_DIR)

	# unpack all archives
	unpack_scene(args.scene_name)
	# find all maya scenes
	maya_scene = util.find_scene('.ma', '.mb', slash_replacer="/", is_maya=True)
	logger.info("Found scene: {}".format(maya_scene))
	
	current_path_for_maya = os.getcwd().replace("\\", "/") + "/"

	# detect project path
	files = os.listdir(os.getcwd())
	zip_file = False
	for file in files:
		if file.endswith(".zip") or file.endswith(".7z"):
			zip_file = True
			project = "/".join(maya_scene.split("/")[:-2])
			
	if not zip_file:
		project = current_path_for_maya

	# read maya template
	maya_script_template = util.read_file("maya_batch_render.py") if args.batchRender == "true" \
		else util.read_file("maya_render.py")
	maya_script = util.format_template_with_args(maya_script_template,
												 res_path=current_path_for_maya,
												 scene_path=maya_scene,
												 project=project)

	# scene name
	filename = os.path.basename(maya_scene).split(".")[0]

	# save render py file
	render_file = util.save_render_file(maya_script, filename, 'py')

	# save bat file
	if args.batchRender == "true":
		cmd_command = '''
			set MAYA_CMD_FILE_OUTPUT=%cd%/Output/render_log.txt
			set MAYA_SCRIPT_PATH=%cd%;%MAYA_SCRIPT_PATH%
			set PYTHONPATH=%cd%;%PYTHONPATH%
			"C:\\Program Files\\Autodesk\\Maya{tool}\\bin\\Render.exe" -r FireRender -s {start_frame} -e {end_frame} -rgb true -preRender "python(\\"import {render_file} as render\\"); python(\\"render.main()\\");" -log "Output\\batch_render_log.txt" -of jpg {maya_scene} 
			'''.format(tool=args.tool, render_file=render_file.split('.')[0], maya_scene=maya_scene, start_frame=args.startFrame, end_frame=args.endFrame)
	else:
		cmd_command = '''
			set MAYA_CMD_FILE_OUTPUT=%cd%/Output/render_log.txt
			set MAYA_SCRIPT_PATH=%cd%;%MAYA_SCRIPT_PATH%
			set PYTHONPATH=%cd%;%PYTHONPATH%
			"C:\\Program Files\\Autodesk\\Maya{tool}\\bin\\Maya.exe" -command "python(\\"import {render_file} as render\\"); python(\\"render.main()\\");" 
			'''.format(tool=args.tool, render_file=render_file.split('.')[0])
	render_bat_file = "launch_render_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)

	# starting rendering
	logger.info("Starting rendering scene: {}".format(maya_scene))
	post_data = {'status': 'Rendering', 'id': args.id}
	util.send_status(post_data)

	# start render monitoring thread
	if args.batchRender == "true":
		monitoring_thread = threading.Thread(target=start_monitor_render_thread, args=(args, util, ))
		monitoring_thread.start()

	# start render
	render_time = 0
	start_time = datetime.datetime.now()
	p = psutil.Popen(render_bat_file, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

	# catch timeout ~30 minutes
	rc = 0
	total_timeout = 70 # ~35 minutes
	error_window = None
	while True:
		try:
			stdout, stderr = p.communicate(timeout=30)
		except (subprocess.TimeoutExpired, psutil.TimeoutExpired) as err:
			total_timeout -= 1
			fatal_errors_titles = ['maya', 'Student Version File', 'Radeon ProRender Error', 'Script Editor', 'File contains mental ray nodes']
			error_window = set(fatal_errors_titles).intersection(get_windows_titles())
			if error_window:
				rc = -1
				for child in reversed(p.children(recursive=True)):
					child.terminate()
				p.terminate()
				break
			elif not total_timeout:
				rc = -2
				break
		else:
			break

	# stop render monitoring thread
	if args.batchRender == "true":
		monitoring_thread.run = False
		monitoring_thread.join()

	render_time += (datetime.datetime.now() - start_time).total_seconds()

	if args.batchRender == "true":
		# fix RPR bug with output files naming
		current_path = str(Path().absolute())
		output_path = os.path.join(current_path, "Output")
		files = os.listdir(output_path)

		for file in files:
			if not file.endswith(".txt"):
				# name.extentions.number -> name_number.extention
				name_parts = file.rsplit(".", 2)
				new_name = name_parts[-3] + "_" + name_parts[-1] + "." + name_parts[-2]
				os.rename(os.path.join(output_path, file), os.path.join(output_path, new_name))

	# update render status
	logger.info("Finished rendering scene: {}".format(maya_scene))
	post_data = {'status': 'Completed', 'id': args.id}
	util.send_status(post_data)

	if args.batchRender == "true":
		# add render time to render info
		with open(os.path.join(".", "render_info.json"), "r") as file:
			data = json.load(file)

		data["render_time"] = round(render_time, 2)

		with open(os.path.join(".", "render_info.json"), "w") as file:
			json.dump(data, file)

	# send render info
	util.send_render_info('render_info.json')

	# send result data
	files = util.create_files_dict(OUTPUT_DIR)
	post_data = util.create_result_status_post_data(rc, OUTPUT_DIR)
	util.send_status(post_data, files)

	return rc


if __name__ == "__main__":
	rc = main()
	exit(rc)
