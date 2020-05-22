import os
import json
import argparse
import subprocess
import psutil
import logging
import traceback
from render_service_scripts.unpack import unpack_all
import shutil
import requests
from requests.auth import HTTPBasicAuth

# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO)
logger = logging.getLogger(__name__)


def send_status(post_data, django_ip, login, password):	
	try_count = 0
	while try_count < 3:
		try:
			response = requests.post(django_ip, data=post_data, auth=HTTPBasicAuth(login, password))
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


def build_viewer_pack(version, filename, args):
		try:
			zip_name = "RPRViewerPack_{}_{}".format(version, filename)	
			shutil.make_archive(zip_name, 'zip', 'viewer_dir')
		except Exception as ex:
			fail_reason = "Zip package build failed"
			logger.error(fail_reason)
			logger.error(str(ex))
			logger.error(traceback.format_exc())	
			post_data = {'status': 'Failure', 'fail_reason': fail_reason, 'id': args.id, 'build_number': args.build_number}
			send_status(post_data, args.django_ip, args.login, args.password)
			exit(-1)


def main(args):
	# find GLTF scene and UIConfig
	gltf_file = ""
	ui_config = ""
	
	for rootdir, dirs, files in os.walk(os.path.join('viewer_dir', 'scene')):
		for file in files:
			if file.endswith('.gltf'):
				gltf_file = os.path.join("scene", file)
			if file.endswith('.json'):
				ui_config = os.path.join("scene", file)

	if gltf_file:
		logger.info("Found scene: " + gltf_file)
	else:
		fail_reason = "No scene in the package"
		logger.error(fail_reason)
		post_data = {'status': 'Failure', 'fail_reason': fail_reason, 'id': args.id, 'build_number': args.build_number}
		send_status(post_data, args.django_ip, args.login, args.password)
		exit(-1)

	# set default
	if ui_config:
		logger.info("Found UI config: " + ui_config)
	else:
		logger.error("No UI config in the package!")

	# read config json file
	if os.path.isfile(os.path.join('viewer_dir', 'config.json')):
		logger.info("Found config file.")
		try:
			with open(os.path.join('viewer_dir', 'config.json')) as f:
				config = json.loads(f.read())
			logger.info("Config file was read successfuly.")
		except Exception as ex:
			logger.error("Config file in corrupted.")
			logger.error(str(ex))
			logger.error(traceback.format_exc())	
	else:
		fail_reason = "Config file in corrupted"
		logger.error(fail_reason)
		post_data = {'status': 'Failure', 'fail_reason': fail_reason, 'id': args.id, 'build_number': args.build_number}
		send_status(post_data, args.django_ip, args.login, args.password)
		exit(-1)

	config['scene']['path'] = gltf_file
	config['screen']['width'] = int(args.width)
	config['screen']['height'] = int(args.height)

	config['engine'] = args.engine
	if args.engine == "hyb":
		config['draw_engine'] = "vw_vulkan"
	elif args.engine in ("rpr", "ogl"):
		config['draw_engine'] = "ogl"
		
	config['uiConfig'] = ui_config

	with open(os.path.join('viewer_dir', 'config.json'), 'w') as f:
		json.dump(config, f, indent=' ', sort_keys=True)
		
	# parse scene name
	filename = args.scene_name.rsplit('.', 1)[0]

	# pack zip
	repeat_launch = False
	for file in os.listdir():
		if file.endswith(".zip"):
			repeat_launch = True

	if not repeat_launch:
		build_viewer_pack(args.version, filename, args)

	config['save_frames'] = True
	config['iterations_per_frame'] = int(args.iterations)
	config['frame_exit_after'] = 1
	with open(os.path.join('viewer_dir', 'config.json'), 'w') as f:
		json.dump(config, f, indent=' ')
	
	# Fix empty stdout 113 line.
	stdout, stderr = (b'', b'')

	#change dir before call viewer (it search config in current dir)
	os.chdir('viewer_dir')

	if os.path.isfile('RadeonProViewer.exe'):
		p = psutil.Popen('RadeonProViewer.exe', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		try:
			stdout, stderr = p.communicate(timeout=int(args.timeout))
		except (subprocess.TimeoutExpired, psutil.TimeoutExpired) as err:
			try:
				for child in reversed(p.children(recursive=True)):
					child.terminate()
				p.terminate()
			except Exception as ex:
				logger.error(str(ex))
				logger.error(traceback.format_exc())	

		with open("viewer_log.txt", 'w', encoding='utf-8') as file:
			stdout = stdout.decode("utf-8")
			file.write(stdout)

		with open("viewer_log.txt", 'a', encoding='utf-8') as file:
			file.write("\n ----STDERR---- \n")
			stderr = stderr.decode("utf-8")
			file.write(stderr)
		
		if not os.path.isfile("img0001.png") and args.engine != "ogl":
			logger.error("Failed to render image! Retry ...")
			#return to workdir
			os.chdir('..')
			raise Exception("No image")
		else:
			logger.info("Testing was finished successfuly.")

	else:
		fail_reason = "No exe file in package"
		logger.error(fail_reason)
		post_data = {'status': 'Failure', 'fail_reason': fail_reason, 'id': args.id, 'build_number': args.build_number}
		send_status(post_data, args.django_ip, args.login, args.password)
		exit(-1)

	#return to workdir
	os.chdir('..')
	
if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument('--id')
	parser.add_argument('--django_ip')
	parser.add_argument('--build_number')
	parser.add_argument('--scene_name')
	parser.add_argument('--version')
	parser.add_argument('--width')
	parser.add_argument('--height')
	parser.add_argument('--engine')
	parser.add_argument('--iterations')
	parser.add_argument('--login')
	parser.add_argument('--password')
	args = parser.parse_args()

	try_count = 0
	# unpack all archives
	unpack_all(os.path.join('.', 'viewer_dir'), delete=True, output_dir=os.path.join('.', 'viewer_dir'))
	while try_count < 3:
		try:
			main(args)
			exit(0)
		except Exception as ex:
			logger.error(str(ex))
			logger.error(traceback.format_exc())
			try_count += 1
			if try_count == 3:
				post_data = {'status': 'Failure', 'fail_reason': str(ex), 'id': args.id, 'build_number': args.build_number}
				send_status(post_data, args.django_ip, args.login, args.password)
				exit(-1)