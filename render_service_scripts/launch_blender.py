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
from render_service_scripts.utils import Util

# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'Output'


def start_error_logs_daemon(stderr, queue):
	for line in iter(stderr.readline, b''):
		queue.put(line)
	stderr.close


def main():
	args = Util.get_render_args()

	util = Util(ip=args.django_ip, logger=logger, args=args)
	# create output folder for images and logs
	util.create_dir(OUTPUT_DIR)

	# unpack all archives
	unpack_scene(args.scene_name)
	# find all blender scenes
	blender_scene = util.find_scene()
	logger.info("Found scene: {}".format(blender_scene))

	# read blender template
	blender_script_template = util.read_file("blender_render.py")

	# format template for current scene
	blender_script = util.format_template_with_args(blender_script_template,
													res_path=os.getcwd(),
													scene_path=blender_scene)

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
	util.send_status(post_data)

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
	timeout = 2000
	start_time = datetime.datetime.now()
	rendered = 0
	with open(os.path.join(OUTPUT_DIR, "render_log.txt"), 'w', encoding='utf-8') as file:
		while (datetime.datetime.now() - start_time).total_seconds() <= timeout:
			output = p.stdout.readline()
			if output:
				line = output.strip().decode("utf-8")
				file.write(line)
				file.write("\n")
				if line.startswith("Fra") and "Samples" in line:
					samples_per_frame = int(line.split("|")[3].strip().rsplit(" ", 1)[-1].split("/")[1])
					all_samples = int(samples_per_frame * (int(args.endFrame) - int(args.startFrame) + 1))
					frame_number = int(line.split(" ", 1)[0].split(":")[1])
					current_samples = int(line.rsplit("|")[3].strip().rsplit(" ", 1)[-1].split("/")[0])
					if frame_number >= int(args.startFrame):
						rendered = (samples_per_frame * (frame_number - int(args.startFrame)) + current_samples) / all_samples * 100
			if p.poll() is not None:
				break
			if rendered != 0 and (datetime.datetime.now() - last_send_status).total_seconds() >= 10:
				post_data = {'status': 'Rendering ( ' + str(round(rendered, 2)) + '% )', 'id': args.id}
				util.send_status(post_data)
				last_send_status = datetime.datetime.now()
		else:
			rc = -1
			for child in reversed(p.children(recursive=True)):
				child.terminate()
			p.terminate()

	# save logs stderr
	with open(os.path.join(OUTPUT_DIR, "render_log.txt"), 'a', encoding='utf-8') as file:
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
	util.send_status(post_data)

	# send render info
	logger.info("Sending render info")
	if os.path.exists("render_info.json"):
		with open("render_info.json") as f:
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

	images = glob.glob(os.path.join(OUTPUT_DIR ,'*.jpg'))
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
