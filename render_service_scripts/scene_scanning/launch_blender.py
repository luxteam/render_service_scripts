import argparse
import logging
import os
import subprocess
import json
import requests

import psutil

from render_service_scripts.unpack import unpack_scene
from render_service_scripts.pack import update_scene_in_archive
from requests.auth import HTTPBasicAuth
import jinja2

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


def send_results(post_data, django_ip, login, password):
	try_count = 0

	headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'Content-Encoding': 'utf-8'}
	while try_count < 3:
		try:
			response = requests.post(django_ip, data=json.dumps(post_data), headers=headers, auth=HTTPBasicAuth(login, password))
			if response.status_code  == 200:
				logger.info("POST request successfuly sent.")
				break
			else:
				logger.info("POST reques failed, status code: " + str(response.status_code))
				break
		except Exception as e:
			if try_count == 2:
				logger.info("POST request try 3 failed. Finishing work.")
				break
			try_count += 1
			logger.info("POST request failed. Retry ...")


def send_scene(post_data, files, django_ip, login, password):
	try_count = 0
	while try_count < 3:
		try:
			response = requests.post(django_ip, data=post_data, files=files, auth=HTTPBasicAuth(login, password))
			if response.status_code  == 200:
				logger.info("POST request successfuly sent.")
				break
			else:
				logger.info("POST reques failed, status code: " + str(response.status_code))
				break
		except Exception as e:
			if try_count == 2:
				logger.info("POST request try 3 failed. Finishing work.")
				break
			try_count += 1
			logger.info("POST request failed. Retry ...")


def main():

	parser = argparse.ArgumentParser()
	parser.add_argument('--django_ip', required=True)
	parser.add_argument('--id', required=True)
	parser.add_argument('--tool', required=True)
	parser.add_argument('--scene_name', required=True)
	parser.add_argument('--login', required=True)
	parser.add_argument('--password', required=True)
	parser.add_argument('--action', required=True)
	parser.add_argument('--configuration_options', required=True)
	parser.add_argument('--options_structure', required=True)
	args = parser.parse_args()

	args.action = args.action.lower()
	configuration_options = json.loads(args.configuration_options)
	options_structure = json.loads(args.options_structure)

	# create output folder for logs
	if not os.path.exists('Output'):
		os.makedirs('Output')

	# unpack all archives
	unpack_scene(args.scene_name)
	# find all blender scenes
	blender_scene = find_blender_scene()
	logger.info("Found scene: {}".format(blender_scene))

	# read or write blender scene scanning template
	env = jinja2.Environment(
		loader=jinja2.PackageLoader('launch_blender', '.'),
		autoescape=True
	)

	blender_script_template = env.get_template("{}_blender_configuration.py".format(args.action))

	# format template for current scene
	if args.action == 'read':
		blender_script = blender_script_template.render(res_path=os.getcwd(), scene_path=blender_scene, options_structure=options_structure)
	elif args.action == 'write':
		blender_script = blender_script_template.render(res_path=os.getcwd(), scene_path=blender_scene, options_structure=options_structure, configuration_options=configuration_options)
	else:
		logger.error("Unknown action: {}".format(args.action))

	# scene name
	split_name = os.path.basename(blender_scene).split(".")
	filename = '.'.join(split_name[0:-1])

	# save py file for scene reading
	render_file = "{action}_{filename}.py".format(action=args.action, filename=filename) 
	with open(render_file, 'w') as f:
		f.write(blender_script)

	# save bat file
	blender_path = "C:\\Program Files\\Blender Foundation\\Blender {tool}\\blender.exe".format(tool=args.tool)
	cmd_command = '"{blender_path}" -b -P "{render_file}"'.format(blender_path=blender_path, render_file=render_file)
	action_bat_file = "launch_{action}_{filename}.bat".format(action=args.action, filename=filename)
	with open(action_bat_file, 'w') as f:
		f.write(cmd_command)

	# starting action
	logger.info("Starting {action} action: {scene}".format(action=args.action, scene=blender_scene))
	p = psutil.Popen(action_bat_file, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	
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

	logger.info("Finished scanning scene: {}".format(blender_scene))

	scene_info_exists = os.path.exists("scene_info.json")

	if rc == 0 and scene_info_exists:
		if args.action == 'write':
			update_scene_in_archive(args.scene_name, os.path.split(blender_scene)[1])
			files = {'scene': open(args.scene_name, 'rb')}

			logger.info("Sending updated scene")
			post_data = {'id': args.id}
			send_scene(post_data, files, args.django_ip, args.login, args.password)

		logger.info("Scanning status: success")

		logger.info("Sending results")

		post_data = {'status': 'Success', 'id': args.id}

		if os.path.exists("scene_info.json"):
			with open("scene_info.json") as file:
				data = json.load(file)

			post_data.update(data)
		
		send_results(post_data, args.django_ip, args.login, args.password)
	else:
		logger.error("Scanning status: failure")
		if rc == -1:
			logger.error("Fail reason: timeout expired")
		elif scene_info_exists:
			logger.error("Fail reason: no output info")
		else:
			rc = -1
			logger.error("Fail reason: unknown")

	return rc

if __name__ == "__main__":
	rc = main()
	exit(rc)
