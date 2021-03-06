import argparse
import os
import subprocess
import psutil
import json
import requests
import glob
import os
import logging
import datetime
from threading import Thread
from queue import Queue, Empty
from render_service_scripts.unpack import unpack_scene
from requests.auth import HTTPBasicAuth

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


def send_results(post_data, files, django_ip, login, password):
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


def start_error_logs_daemon(stderr, queue):
	for line in iter(stderr.readline, b''):
		queue.put(line)
	stderr.close


def main():

	parser = argparse.ArgumentParser()
	parser.add_argument('--django_ip', required=True)
	parser.add_argument('--id', required=True)
	parser.add_argument('--tool', required=True)
	parser.add_argument('--engine', required=True)
	parser.add_argument('--min_samples', required=True)
	parser.add_argument('--max_samples', required=True)
	parser.add_argument('--noise_threshold', required=True)
	parser.add_argument('--startFrame', required=True)
	parser.add_argument('--endFrame', required=True)
	parser.add_argument('--width', required=True)
	parser.add_argument('--height', required=True)
	parser.add_argument('--scene_name', required=True)
	parser.add_argument('--login', required=True)
	parser.add_argument('--password', required=True)
	parser.add_argument('--timeout', required=True)
	args = parser.parse_args()

	# create output folder for images and logs
	if not os.path.exists('Output'):
		os.makedirs('Output')

	# unpack all archives
	unpack_scene(args.scene_name)
	# find all blender scenes
	blender_scene = find_blender_scene()
	logger.info("Found scene: {}".format(blender_scene))

	# read blender template
	with open ("blender_render.py") as f:
		blender_script_template = f.read()

	# format template for current scene
	blender_script = blender_script_template.format(min_samples=args.min_samples, max_samples=args.max_samples, noise_threshold=args.noise_threshold, \
		width = args.width, height = args.height, res_path=os.getcwd(), startFrame=args.startFrame, endFrame=args.endFrame, scene_path=blender_scene, engine=args.engine)

	# scene name
	split_name = os.path.basename(blender_scene).split(".")
	filename = '.'.join(split_name[0:-1])

	# save render py file
	render_file = "render_{}.py".format(filename) 
	with open(render_file, 'w') as f:
		f.write(blender_script)

	# save bat file
	blender_path = "C:\\Program Files\\Blender Foundation\\Blender {tool}\\blender.exe".format(tool=args.tool)
	cmd_command = '"{blender_path}" -b -P "{render_file}"'.format(blender_path=blender_path, render_file=render_file)
	render_bat_file = "launch_render_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)

	# starting rendering
	logger.info("Starting rendering scene: {}".format(blender_scene))
	post_data = {'status': 'Rendering', 'id': args.id}
	send_status(post_data, args.django_ip, args.login, args.password)

	last_send_status = datetime.datetime.now()

	# starting rendering
	logger.info("Starting rendering scene: {}".format(blender_scene))

	# start render
	p = psutil.Popen(render_bat_file, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

	# start error logs daemon
	queue = Queue()
	thread = Thread(target=start_error_logs_daemon, args=(p.stderr, queue))
	thread.daemon = True
	thread.start()
	
	# catch timeout ~30 minutes
	rc = 0
	timeout = int(args.timeout)
	start_time = datetime.datetime.now()
	rendered = 0
	with open(os.path.join('Output', "render_log.txt"), 'w', encoding='utf-8') as file:
		while (datetime.datetime.now() - start_time).total_seconds() <= timeout:
			output = p.stdout.readline()
			if output:
				line = output.strip().decode("utf-8")
				file.write(line)
				file.write("\n")
				if line.startswith("Fra") and "Samples" in line:
					samples_per_frame = int(line.split("|")[3].strip().rsplit(" ", 1)[-1].split("/")[1].split(".")[0])
					all_samples = int(samples_per_frame * (int(args.endFrame) - int(args.startFrame) + 1))
					frame_number = int(line.split(" ", 1)[0].split(":")[1])
					current_samples = int(line.rsplit("|")[3].strip().rsplit(" ", 1)[-1].split("/")[0])
					if frame_number >= int(args.startFrame):
						rendered = (samples_per_frame * (frame_number - int(args.startFrame)) + current_samples) / all_samples * 100
			if p.poll() is not None:
				break
			if rendered != 0 and (datetime.datetime.now() - last_send_status).total_seconds() >= 10:
				post_data = {'status': 'Rendering ( ' + str(round(rendered, 2)) + '% )', 'id': args.id}
				send_status(post_data, args.django_ip, args.login, args.password)
				last_send_status = datetime.datetime.now()
		else:
			rc = -1
			for child in reversed(p.children(recursive=True)):
				child.terminate()
			p.terminate()		

	# save logs stderr
	with open(os.path.join('Output', "render_log.txt"), 'a', encoding='utf-8') as file:
		file.write("\n ----STEDERR---- \n")
		while True:
			try:
				line = queue.get_nowait().decode("utf-8")
				file.write(line)
			except Empty:
				break

	# update render status
	logger.info("Finished rendering scene: {}".format(blender_scene))
	post_data = {'status': 'Completed', 'id': args.id}
	send_status(post_data, args.django_ip, args.login, args.password)

	# send render info
	logger.info("Sending render info")
	if os.path.exists("render_info.json"):
		with open("render_info.json") as f:
			data = json.loads(f.read())

		post_data = {'render_time': data['render_time'], 'width': data['width'], 'height': data['height'], 'min_samples': data['min_samples'], \
			'max_samples': data['max_samples'], 'noise_threshold': data['noise_threshold'], 'id': args.id, 'status':'render_info'}
		send_status(post_data, args.django_ip, args.login, args.password)
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

	images = glob.glob(os.path.join('Output' ,'*.jpg'))
	images.extend(glob.glob(os.path.join('Output' ,'*.png')))
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
	post_data = {'status': status, 'fail_reason': fail_reason, 'id': args.id}
	send_results(post_data, files, args.django_ip, args.login, args.password)

	return rc

if __name__ == "__main__":
	rc = main()
	exit(rc)
