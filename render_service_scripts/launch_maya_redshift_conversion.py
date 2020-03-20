import argparse
import os
import subprocess
import psutil
import requests
import json
import datetime
import glob
import os
import logging
import ctypes
from render_service_scripts.unpack import unpack_scene
from render_service_scripts import utils


# logging
logging.basicConfig(filename="launch_conversion_log.txt", level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'Output'


def get_rs_render_time(log_name):
	with open(log_name, 'r') as file:
		for line in file.readlines():
			if "[Redshift] Rendering done - total time for 1 frames:" in line:
				time_s = line.split(": ")[-1]

				try:
					x = datetime.datetime.strptime(time_s.replace('\n', '').replace('\r', ''), '%S.%fs')
				except ValueError:
					x = datetime.datetime.strptime(time_s.replace('\n', '').replace('\r', ''), '%Mm:%Ss')
				# 	TODO: proceed H:M:S

				return float(x.second + x.minute * 60 + float(x.microsecond / 1000000))


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

	parser = argparse.ArgumentParser()
	parser.add_argument('--django_ip', required=True)
	parser.add_argument('--id', required=True)
	parser.add_argument('--build_number', required=True)
	parser.add_argument('--tool', required=True)
	parser.add_argument('--scene_name', required=True)
	args = parser.parse_args()

	# create utils object
	util = utils.Util(ip=args.django_ip, logger=logger)

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
	redshift_script_template = util.read_file("conversion_redshift_render.py")

	redshift_script = redshift_script_template.format(res_path=current_path_for_maya, scene_path=maya_scene, project=project)

	# scene name
	filename = os.path.basename(maya_scene).split(".")[0]

	# save render py file
	redshift_render_file = "render_redshift_{}.py".format(filename) 
	with open(redshift_render_file, 'w') as f:
		f.write(redshift_script)

	# Redshift batch render
	cmd_command = '''
		set MAYA_CMD_FILE_OUTPUT=%cd%/Output/maya_redshift_render_log.txt
		set MAYA_SCRIPT_PATH=%cd%;%MAYA_SCRIPT_PATH%
		set PYTHONPATH=%cd%;%PYTHONPATH%
		"C:\\Program Files\\Autodesk\\Maya{tool}\\bin\\Render.exe" -r redshift -preRender "python(\\"import {redshift_render_file} as render\\"); python(\\"render.main()\\");" -log "Output\\batch_redshift_render_log.txt" -of jpg {maya_scene}
		'''.format(tool=args.tool, maya_scene=maya_scene, redshift_render_file=redshift_render_file.split('.')[0])
	render_bat_file = "launch_redshift_render_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)		

	# starting rendering
	logger.info("Starting rendering redshift scene: {}".format(maya_scene))
	post_data = {'status': 'Rendering redshift', 'id': args.id}
	util.send_status(post_data)

	# start render
	p = psutil.Popen(render_bat_file, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

	# catch timeout ~30 minutes
	rc = 0
	try:
		stdout, stderr = p.communicate(timeout=2000)
	except (subprocess.TimeoutExpired, psutil.TimeoutExpired) as err:
		rc = -3
		for child in reversed(p.children(recursive=True)):
			child.terminate()
		p.terminate()

	# update render status
	logger.info("Finished rendering redshift scene: {}".format(maya_scene))
	logger.info("Starting converting redshift scene: {}".format(maya_scene))
	post_data = {'status': 'Converting redshift', 'id': args.id}
	util.send_status(post_data)

	# send render info
	logger.info("Sending render info")
	redshift_render_time = 0
	try:
		redshift_render_time = round(get_rs_render_time(os.path.join("Output", "batch_redshift_render_log.txt")), 2)
		post_data = {'redshift_render_time': redshift_render_time, 'id': args.id, 'status':'redshift_render_info'}
		util.send_status(post_data)
	except:
		logger.info("Error. No render time!")

	# read RPR template
	rpr_script_template = util.read_file("conversion_rpr_render.py")
	
	rpr_script = rpr_script_template.format(res_path=current_path_for_maya, scene_path=maya_scene, project=project)

	# save render py file
	render_rpr_file = "render_rpr_{}.py".format(filename) 
	with open(render_rpr_file, 'w') as f:
		f.write(rpr_script)

	# save bat file
	cmd_command = '''
		set MAYA_CMD_FILE_OUTPUT=%cd%/Output/rpr_render_log.txt
		set MAYA_SCRIPT_PATH=%cd%;%MAYA_SCRIPT_PATH%
		set PYTHONPATH=%cd%;%cd%/RS2RPRConvertTool;%PYTHONPATH%
		"C:\\Program Files\\Autodesk\\Maya{tool}\\bin\\Maya.exe" -command "python(\\"import {render_rpr_file} as render\\"); python(\\"render.main()\\");" 
		'''.format(tool=args.tool, render_rpr_file=render_rpr_file.split('.')[0])
	render_bat_file = "launch_rpr_render_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)

	# starting rendering
	logger.info("Starting rendering rpr scene: {}".format(maya_scene))
	post_data = {'status': 'Rendering RPR', 'id': args.id}
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

	# update render status
	logger.info("Finished rendering rpr scene: {}".format(maya_scene))
	post_data = {'status': 'Completed', 'id': args.id}
	util.send_status(post_data)

	# send render info
	logger.info("Sending rpr render info")
	if os.path.exists("rpr_render_info.json"):
		data = json.loads(util.read_file("rpr_render_info.json"))
		post_data = {'rpr_render_time': data['rpr_render_time'], 'id': args.id, 'status':'rpr_render_info'}
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

	images = glob.glob(os.path.join(OUTPUT_DIR ,'*.jpg'))
	if rc == 0 and len(images) > 1:
		logger.info("Render status: success")
		status = "Success"
	else:
		logger.info("Render status: failure")
		status = "Failure"
		if rc == -1:
			logger.info("Fail reason: redshift timeout expired")
			fail_reason = "Redshift timeout expired"
		elif rc == -1:
			rc = -1
			logger.info("crash window - {}".format(list(error_window)[0]))
			fail_reason = "crash window - {}".format(list(error_window)[0])
		elif rc == -3:
			logger.info("Fail reason: rpr timeout expired")
			fail_reason = "RPR timeout expired"
		elif len(images) < 2:
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
