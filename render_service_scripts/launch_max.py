import argparse
import sys
import os
import subprocess
import psutil
import json
import ctypes
import requests
import glob
import logging
from render_service_scripts.unpack import unpack_scene
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


def main():
	args = Util.get_render_args()

	# create utils object
	util = Util(ip=args.django_ip, logger=logger)

	# create output folder for images and logs
	util.create_dir(OUTPUT_DIR)

	# unpack all archives
	unpack_scene(args.scene_name)
	# find all blender scenes
	max_scene = util.find_scene('.max', slash_replacer='\\\\')
	logger.info("Found scene: {}".format(max_scene))

	current_path_for_max = os.getcwd().replace("\\", "\\\\")

	# read maya template
	max_script_template = util.read_file("max_render.ms")
	
	max_script = max_script_template.format(min_samples=args.min_samples, max_samples=args.max_samples, noise_threshold=args.noise_threshold, \
		width = args.width, height = args.height, res_path=current_path_for_max, startFrame=args.startFrame, endFrame=args.endFrame, scene_path=max_scene)

	# scene name
	filename = os.path.basename(max_scene).split(".")[0]

	# save render py file
	render_file = "render_{}.ms".format(filename) 
	with open(render_file, 'w') as f:
		f.write(max_script)

	# save bat file
	cmd_command = '''
		"C:\\Program Files\\Autodesk\\3ds Max {tool}\\3dsmax.exe" -U MAXScript "{render_file}" -silent
		'''.format(tool=args.tool, render_file=render_file)
	render_bat_file = "launch_render_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)

	# starting rendering
	logger.info("Starting rendering scene: {}".format(max_scene))
	post_data = {'status': 'Rendering', 'id': args.id}
	util.send_status(post_data)

	# start render
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
			fatal_errors_titles = ['Radeon ProRender', 'AMD Radeon ProRender debug assert', os.getcwd() + ' - MAXScript',\
			'3ds Max', 'Microsoft Visual C++ Runtime Library', \
			'3ds Max Error Report', '3ds Max application', 'Radeon ProRender Error', 'Image I/O Error', 'Warning', 'Error']
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


	# update render status
	logger.info("Finished rendering scene: {}".format(max_scene))
	post_data = {'status': 'Completed', 'id': args.id}
	util.send_status(post_data)

	# send render info
	logger.info("Sending render info")
	if os.path.exists("render_info.json"):
		data = json.loads(util.read_file("render_info.json"))
		post_data = {'render_time': data['render_time'], 'width': data['width'], 'height': data['height'], 'min_samples': data['min_samples'], \
			'max_samples': data['max_samples'], 'noise_threshold': data['noise_threshold'], 'id': args.id, 'status':'render_info'}
		util.send_status(post_data)
	else:
		logger.info("Error. No render info!")

	# preparing dict with output files for post
	files = {}
	output_files = os.listdir(OUTPUT_DIR)
	for output_file in output_files:
		files.update({output_file: open(os.path.join(OUTPUT_DIR, output_file), 'rb')})
	logger.info("Output files: {}".format(files))

	# detect render status
	status = "Unknown"
	fail_reason = "Unknown"

	images = glob.glob(os.path.join(OUTPUT_DIR, '*.jpg'))
	if rc == 0 and images:
		logger.info("Render status: success")
		status = "Success"
	else:
		logger.info("rc: {}".format(str(rc)))
		logger.info("Render status: failure")
		status = "Failure"
		if rc == -2:
			logger.info("Fail reason: timeout expired")
			fail_reason = "Timeout expired"
		elif rc == -1:
			rc = -1
			logger.info("crash window - {}".format(list(error_window)[0]))
			fail_reason = "crash window - {}".format(list(error_window)[0])
		elif not images:
			rc = -1
			logger.info("Fail reason: rendering failed, no output image")
			fail_reason = "No output image"
		else:
			rc = -1
			logger.info("Fail reason: unknown")
			fail_reason = "Unknown"

	logger.info("Sending results")
	post_data = {'status': status, 'fail_reason': fail_reason, 'id': args.id, 'build_number': args.build_number}
	util.send_status(post_data, files)

	return rc


if __name__ == "__main__":
	rc = main()
	exit(rc)
