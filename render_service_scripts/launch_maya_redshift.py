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
from render_service_scripts.unpack import unpack_scene
from render_service_scripts.utils import Util

# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO,
					format='%(asctime)s :: %(levelname)s :: %(message)s')
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


def main():
	args = Util.get_render_args()

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
	maya_script_template = util.read_file("redshift_render.py")
	maya_script = util.format_template_with_args(maya_script_template,
												 res_path=current_path_for_maya,
												 scene_path=maya_scene,
												 project=project)

	# scene name
	filename = os.path.basename(maya_scene).split(".")[0]

	# save render py file
	render_file = util.save_render_file(maya_script, filename, 'py')

	# Redshift batch render
	cmd_command = '''
		set MAYA_CMD_FILE_OUTPUT=%cd%/Output/maya_render_log.txt
		set MAYA_SCRIPT_PATH=%cd%;%MAYA_SCRIPT_PATH%
		set PYTHONPATH=%cd%;%PYTHONPATH%
		"C:\\Program Files\\Autodesk\\Maya{tool}\\bin\\Render.exe" -r redshift -preRender "python(\\"import {render_file} as render\\"); python(\\"render.main()\\");" -log "Output\\batch_render_log.txt" -of jpg {maya_scene}
		'''.format(tool=args.tool, maya_scene=maya_scene, render_file=render_file.split('.')[0])
	render_bat_file = "launch_render_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)

	# starting rendering
	logger.info("Starting rendering scene: {}".format(maya_scene))
	post_data = {'status': 'Rendering', 'id': args.id}
	util.send_status(post_data)

	# start render
	p = psutil.Popen(render_bat_file, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

	# catch timeout ~30 minutes
	rc = 0
	try:
		stdout, stderr = p.communicate(timeout=2000)
	except (subprocess.TimeoutExpired, psutil.TimeoutExpired) as err:
		rc = -1
		for child in reversed(p.children(recursive=True)):
			child.terminate()
		p.terminate()

	# update render status
	logger.info("Finished rendering scene: {}".format(maya_scene))
	post_data = {'status': 'Completed', 'id': args.id}
	util.send_status(post_data)

	# send render info
	logger.info("Sending render info")
	if os.path.exists("render_info.json"):
		render_time = 0
		try:
			render_time = round(get_rs_render_time(os.path.join("Output", "maya_render_log.txt")), 2)
		except:
			logger.info("Error. No render time!")

		data = json.loads(util.read_file("render_info.json"))

		post_data = {'render_time': render_time, 'width': data['width'], 'height': data['height'],
					 'min_samples': data['min_samples'], \
					 'max_samples': data['max_samples'], 'noise_threshold': data['noise_threshold'], 'id': args.id,
					 'status': 'render_info'}
		util.send_status(post_data)
	else:
		logger.info("Error. No render info!")

	# preparing dict with output files for post
	files = {}
	output_files = os.listdir('Output')
	for output_file in output_files:
		files.update({output_file: open(os.path.join('Output', output_file), 'rb')})
	logger.info("Output files: {}".format(files))

	# detect render status
	status = "Unknown"
	fail_reason = "Unknown"

	images = glob.glob(os.path.join('Output', '*.jpg'))
	if rc == 0 and images:
		logger.info("Render status: success")
		status = "Success"
	else:
		logger.info("Render status: failure")
		status = "Failure"
		if rc == -1:
			logger.info("Fail reason: timeout expired")
			fail_reason = "Timeout expired"
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
