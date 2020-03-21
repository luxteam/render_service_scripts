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
from render_service_scripts.utils import BlenderLauncher

# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'Output'


def start_error_logs_daemon(stderr, queue):
	for line in iter(stderr.readline, b''):
		queue.put(line)
	stderr.close


def main():
	launcher = BlenderLauncher(logger, OUTPUT_DIR)
	launcher.prepare_launch()
	args = launcher.args
	util = launcher.util
	filename = launcher.scene_file_name
	render_file = launcher.render_file

	# save bat file
	blender_path = "C:\\Program Files\\Blender Foundation\\Blender {tool}\\blender.exe".format(tool=args.tool)
	cmd_command = '"{blender_path}" -b -P "{render_file}"'.format(blender_path=blender_path, render_file=render_file)
	render_bat_file = "launch_render_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)

	launcher.send_start_rendering()

	last_send_status = datetime.datetime.now()

	# start render
	p = util.start_render(render_bat_file)

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

	launcher.send_finish_rendering()
	rc = launcher.send_result_data(rc)

	return rc


if __name__ == "__main__":
	rc = main()
	exit(rc)
