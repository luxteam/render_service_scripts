import argparse
import logging
import os
import subprocess

import psutil

from render_service_scripts.unpack import unpack_scene

# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)


def find_blender_scene():
	scene = []
	for rootdir, dirs, files in os.walk(os.getcwd()):
		for file in files:
			if file.endswith('.blend'):
				scene.append(os.path.join(rootdir, file))

	return scene[0]


def main():

	parser = argparse.ArgumentParser()
	parser.add_argument('--django_ip', required=True)
	parser.add_argument('--id', required=True)
	parser.add_argument('--tool', required=True)
	parser.add_argument('--scene_name', required=True)
	parser.add_argument('--login', required=True)
	parser.add_argument('--password', required=True)
	args = parser.parse_args()

	# create output folder for logs
	if not os.path.exists('Output'):
		os.makedirs('Output')

	# unpack all archives
	unpack_scene(args.scene_name)
	# find all blender scenes
	blender_scene = find_blender_scene()
	logger.info("Found scene: {}".format(blender_scene))

	# read blender scene scanning template
	with open ("read_blender_configuration.py") as f:
		blender_script_template = f.read()

	# format template for current scene
	blender_script = blender_script_template.format(res_path=os.getcwd(), scene_path=blender_scene)

	# scene name
	split_name = os.path.basename(blender_scene).split(".")
	filename = '.'.join(split_name[0:-1])

	# save py file for scene reading
	render_file = "read_{}.py".format(filename) 
	with open(render_file, 'w') as f:
		f.write(blender_script)

	# save bat file
	blender_path = "C:\\Program Files\\Blender Foundation\\Blender {tool}\\blender.exe".format(tool=args.tool)
	cmd_command = '"{blender_path}" -b -P "{render_file}"'.format(blender_path=blender_path, render_file=render_file)
	render_bat_file = "launch_read_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)

	# starting scanning
	logger.info("Starting scanning scene: {}".format(blender_scene))

	# start render
	p = psutil.Popen(render_bat_file, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	
	# catch timeout (30 minutes)
	timeout = 1800
	rc = 0
	try:
		stdout, stderr = p.communicate(timeout=timeout)
	except (subprocess.TimeoutExpired, psutil.TimeoutExpired) as err:
		rc = -1
		for child in reversed(p.children(recursive=True)):
			child.terminate()
		p.terminate()


	# save logs
	with open(os.path.join('Output', "render_log.txt"), 'w', encoding='utf-8') as file:
		stdout = stdout.decode("utf-8")
		file.write(stdout)

	with open(os.path.join('Output', "render_log.txt"), 'a', encoding='utf-8') as file:
		file.write("\n ----STEDERR---- \n")
		stderr = stderr.decode("utf-8")
		file.write(stderr)

	# update render status
	logger.info("Finished scanning scene: {}".format(blender_scene))
	# TODO collect and send data to render service

	# detect render status
	status = "Unknown"
	fail_reason = "Unknown"

	if rc == 0:
		logger.info("Render status: success")
		status = "Success"
	else:
		logger.info("Render status: failure")
		status = "Failure"
		if rc == -1:
			logger.info("Fail reason: timeout expired")
			fail_reason = "Timeout expired"
		else:
			logger.info("Fail reason: unknown")
			fail_reason = "Unknown"

	return rc

if __name__ == "__main__":
	rc = main()
	exit(rc)
