import subprocess
import psutil
import os
import logging
import datetime
import threading
from time import sleep
from file_read_backwards import FileReadBackwards
from pathlib import Path
from render_service_scripts.utils import MayaLauncher


# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'Output'


def start_monitor_render_thread(args, util):
	post_data = {'status': 'Rendering', 'id': args.id}
	util.send_status(post_data)
	thread = threading.currentThread()
	delay = 10
	log_file = os.path.join(OUTPUT_DIR, "batch_render_log.txt")
	all_frames = int(args.endFrame) - int(args.startFrame) + 1
	while getattr(thread, "run", True):
		try :
			with FileReadBackwards(log_file, encoding="utf-8") as file:
				for line in file:
					if "Percentage of rendering done" in line:
						frame_number = int(line.split("(", 1)[1].split(",", 1)[0].split(" ", 1)[1])
						current_percentage = int(line.rsplit(":", 1)[1].strip().split(" ", 1)[0])
						rendered = ((frame_number - int(args.startFrame)) * 100 + current_percentage) / (all_frames * 100) * 100
						status = 'Rendering ( ' + str(round(rendered, 2)) + '% )'
						post_data = {'status': status, 'id': args.id}
						util.send_status(post_data)
						break
		except FileNotFoundError:
			pass
		sleep(10)


def main():
	launcher = MayaLauncher(logger, OUTPUT_DIR)
	launcher.prepare_launch()
	args = launcher.args
	util = launcher.util
	maya_scene = launcher.scene
	filename = launcher.scene_file_name
	render_file = util.get_file_name(launcher.render_file)

	# save bat file
	if args.batchRender == "true":
		cmd_command = '''
			set MAYA_CMD_FILE_OUTPUT=%cd%/Output/render_log.txt
			set MAYA_SCRIPT_PATH=%cd%;%MAYA_SCRIPT_PATH%
			set PYTHONPATH=%cd%;%PYTHONPATH%
			"C:\\Program Files\\Autodesk\\Maya{tool}\\bin\\Render.exe" -r FireRender -s {start_frame} -e {end_frame} -rgb true -preRender "python(\\"import {render_file} as render\\"); python(\\"render.main()\\");" -log "Output\\batch_render_log.txt" -of jpg {maya_scene} 
			'''.format(tool=args.tool, render_file=render_file, maya_scene=maya_scene, start_frame=args.startFrame, end_frame=args.endFrame)
	else:
		cmd_command = '''
			set MAYA_CMD_FILE_OUTPUT=%cd%/Output/render_log.txt
			set MAYA_SCRIPT_PATH=%cd%;%MAYA_SCRIPT_PATH%
			set PYTHONPATH=%cd%;%PYTHONPATH%
			"C:\\Program Files\\Autodesk\\Maya{tool}\\bin\\Maya.exe" -command "python(\\"import {render_file} as render\\"); python(\\"render.main()\\");" 
			'''.format(tool=args.tool, render_file=render_file)
	render_bat_file = "launch_render_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)

	# send starting rendering
	launcher.send_start_rendering()

	# start render monitoring thread
	if args.batchRender == "true":
		monitoring_thread = threading.Thread(target=start_monitor_render_thread, args=(args, util, ))
		monitoring_thread.start()

	# start render
	render_time = 0
	start_time = datetime.datetime.now()
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
			fatal_errors_titles = ['maya', 'Student Version File', 'Radeon ProRender Error', 'Script Editor', 'File contains mental ray nodes']
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

	# stop render monitoring thread
	if args.batchRender == "true":
		monitoring_thread.run = False
		monitoring_thread.join()

	render_time += (datetime.datetime.now() - start_time).total_seconds()

	if args.batchRender == "true":
		# fix RPR bug with output files naming
		current_path = str(Path().absolute())
		output_path = os.path.join(current_path, "Output")
		files = os.listdir(output_path)

		for file in files:
			if not file.endswith(".txt"):
				# name.extentions.number -> name_number.extention
				name_parts = file.rsplit(".", 2)
				new_name = name_parts[-3] + "_" + name_parts[-1] + "." + name_parts[-2]
				os.rename(os.path.join(output_path, file), os.path.join(output_path, new_name))

	# update render status
	launcher.send_finish_rendering()

	# send render info
	if args.batchRender == "true":
		util.send_render_info('render_info.json', render_time=round(render_time, 2))
	else:
		util.send_render_info('render_info.json')

	rc = launcher.send_result_data(rc)

	return rc


if __name__ == "__main__":
	rc = main()
	exit(rc)
