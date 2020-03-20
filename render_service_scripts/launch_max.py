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


def main():
	args = Util.get_render_args()

	# create utils object
	util = Util(ip=args.django_ip, logger=logger, args=args)

	# create output folder for images and logs
	util.create_dir(OUTPUT_DIR)

	# unpack all archives
	unpack_scene(args.scene_name)
	# find all blender scenes
	max_scene = util.find_scene('.max', slash_replacer='\\\\')
	logger.info("Found scene: {}".format(max_scene))

	current_path_for_max = os.getcwd().replace("\\", "\\\\")

	# read max template
	max_script_template = util.read_file("max_render.ms")
	max_script = util.format_template_with_args(max_script_template,
												 res_path=current_path_for_max,
												 scene_path=max_scene)
	# scene name
	filename = os.path.basename(max_scene).split(".")[0]

	# save render py file
	render_file = util.save_render_file(max_script, filename, 'ms')

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
	p = util.start_render(render_bat_file)

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
			error_window = set(fatal_errors_titles).intersection(util.get_windows_titles())
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

	util.send_render_info('render_info.json')

	# send result data
	files = util.create_files_dict(OUTPUT_DIR)
	rc, post_data = util.create_result_status_post_data(rc, OUTPUT_DIR)
	util.send_status(post_data, files)

	return rc


if __name__ == "__main__":
	rc = main()
	exit(rc)
