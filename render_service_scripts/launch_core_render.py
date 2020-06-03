import argparse
import sys
import os
import re
import subprocess
import psutil
import json
import requests
import logging
import glob
from render_service_scripts.unpack import unpack_scene
from requests.auth import HTTPBasicAuth

# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)


def parse_scenename(name):
	split_name = name.split('.')
	filename = '.'.join(split_name[0:-1])
	ext = split_name[-1]
	return filename, ext


def str_to_raw(s):
    raw_map = {8:r'\b', 7:r'\a', 12:r'\f', 10:r'\n', 13:r'\r', 9:r'\t', 11:r'\v'}
    return r''.join(i if ord(i) > 32 else raw_map.get(ord(i), i) for i in s)


def getScenes(folder):
	scenes = []
	for rootdir, dirs, files in os.walk(folder):
		for file in files:
			if file.endswith('.rpr') or file.endswith('.gltf'):
				scenes.append(os.path.join(rootdir, file))

	return scenes


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


def configure_json(args):
		config_json = {}
		config_json["width"] = int(args.width)
		config_json["height"] = int(args.height)
		config_json["iterations"] = int(args.pass_limit)
		config_json["threads"] = 4
		config_json["context"] = {
			"gpu0": 1 if 'gpu0' in args.gpu else 0,
			"gpu1": 1 if 'gpu1' in args.gpu else 0,
			"gpu2": 1 if 'gpu2' in args.gpu else 0,
			"gpu3": 1 if 'gpu3' in args.gpu else 0,
			"gpu4": 1 if 'gpu4' in args.gpu else 0,
			"gpu5": 1 if 'gpu5' in args.gpu else 0,
			"threads": 16,
			"debug": 0
		}
		return config_json


def save_configured_files(ScriptPath, config_json, cmdScriptPath, cmdRun):
	try:
		with open(ScriptPath, 'w') as f:
			json.dump(config_json, f, indent=4)
		with open(cmdScriptPath, 'w') as f:
			f.write(cmdRun)
	except OSError as err:
		pass


def update_core_log(stdout, stderr):
	with open(os.path.join('Output', "core_log.txt"), 'a', encoding='utf-8') as file:
		stdout = stdout.decode("utf-8")
		file.write(stdout)

	with open(os.path.join('Output', "core_log.txt"), 'a', encoding='utf-8') as file:
		file.write("\n ----STEDERR---- \n")
		stderr = stderr.decode("utf-8")
		file.write(stderr)


def main():

	parser = argparse.ArgumentParser()

	parser.add_argument('--django_ip', required=True)
	parser.add_argument('--id', required=True)
	parser.add_argument('--pass_limit', required=True)
	parser.add_argument('--width', required=True)
	parser.add_argument('--height', required=True)
	parser.add_argument('--sceneName', required=True)
	parser.add_argument('--startFrame', required=True)
	parser.add_argument('--endFrame', required=True)
	parser.add_argument('--gpu', required=True)
	parser.add_argument('--login', required=True)
	parser.add_argument('--password', required=True)
	parser.add_argument('--timeout', required=True)

	args = parser.parse_args()

	startFrame = int(args.startFrame)
	endFrame = int(args.endFrame)

	current_path = os.getcwd()
	if not os.path.exists('Output'):
		os.makedirs('Output')
	output_path = os.path.join(current_path, "Output")

	unpack_scene(args.sceneName)
	scenes = getScenes(current_path)

	timeout = int(args.timeout) / len(scenes)
	render_time = 0

	if startFrame == 1 and endFrame == 1:
		animation = False
	else:
		animation = True

	invalid_rcs = 0	

	# single rpr file
	if len(scenes) == 1:
		sceneName = os.path.basename(str_to_raw(args.sceneName))
		file_name, file_format = parse_scenename(sceneName)

		config_json = configure_json(args)
		config_json["output"] = os.path.join(output_path, file_name + ".png")
		config_json["output.json"] = os.path.join(output_path, file_name + ".json")

		ScriptPath = os.path.join(current_path, "cfg_{}.json".format(file_name))
		cmdRun = '"{tool}" "{scene}" "{template}"\n'.format(tool="C:\\rprSdkWin64\\RprsRender64.exe", scene=scenes[0], template=ScriptPath)
		cmdScriptPath = os.path.join(current_path, '{}.bat'.format(file_name))

		save_configured_files(ScriptPath, config_json, cmdScriptPath, cmdRun)

		p = psutil.Popen(cmdScriptPath, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		stdout, stderr = p.communicate()

		update_core_log(stdout, stderr)

		try:
			p.wait(timeout=timeout)
		except psutil.TimeoutExpired as err:
			invalid_rcs = 1
			for child in reversed(p.children(recursive=True)):
				child.terminate()
			p.terminate()

		# get render time
		try:
			with open(os.path.join(output_path, file_name + ".json")) as f:
				data = json.loads(f.read().replace("\\", "\\\\"))
			render_time = data['render.time.ms'] / 1000
		except:
			print("Error render")

	elif len(scenes) > 1 and animation:
		sceneName = os.path.basename(str_to_raw(args.sceneName))
		file_name, file_format = parse_scenename(sceneName)

		for frame in range(startFrame, endFrame + 1):
			post_data = {'status': 'Rendering. Current frame №' + str(frame), 'id': args.id}
			send_status(post_data, args.django_ip, args.login, args.password)

			config_json = configure_json(args)
			config_json["output"] = os.path.join(output_path, file_name + "_" + str(frame).zfill(3) + ".png")
			config_json["output.json"] = os.path.join(output_path, file_name + "_" + str(frame).zfill(3) + ".json")

			scene_name = scenes[0].split("\\")[-1].split(".")[0]
			scene = scenes[0].replace(scene_name, file_name + "_" + str(frame))	

			ScriptPath = os.path.join(current_path, "cfg_{}.json".format(file_name + "_" + str(frame)))
			cmdRun = '"{tool}" "{scene}" "{template}"\n'.format(tool="C:\\rprSdkWin64\\RprsRender64.exe", scene=scene, template=ScriptPath)
			cmdScriptPath = os.path.join(current_path, '{}.bat'.format(file_name + "_" + str(frame)))
			
			save_configured_files(ScriptPath, config_json, cmdScriptPath, cmdRun)

			p = psutil.Popen(cmdScriptPath, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			stdout, stderr = p.communicate()

			update_core_log(stdout, stderr)

			try:
				p.wait(timeout=timeout)
			except psutil.TimeoutExpired as err:
				invalid_rcs += 1
				for child in reversed(p.children(recursive=True)):
					child.terminate()
				p.terminate()

			# get render time
			try:
				with open(os.path.join(output_path, file_name + "_" + str(frame).zfill(3) + ".json")) as f:
					data = json.loads(f.read().replace("\\", "\\\\"))
				render_time += data['render.time.ms'] / 1000
			except:
				print("Error render")

	else:
		scenes_rendered = 0
		for scene in scenes:
			post_data = {'status': 'Rendering (' + str(scenes_rendered) + ' of ' + str(len(scenes)) + ')', 'id': args.id}
			send_status(post_data, args.django_ip, args.login, args.password)

			sceneName = os.path.basename(str_to_raw(scene))
			file_name, file_format = parse_scenename(sceneName)

			frame = re.findall(r'_\d+', file_name)
			if frame:
				frame = int(frame[-1][1:])
				file_name = '_'.join(sceneName.split("_")[0:-1]) + '_' + str(frame).zfill(3)

			config_json = configure_json(args)
			config_json["output"] = os.path.join(output_path, file_name + ".png")
			config_json["output.json"] = os.path.join(output_path, file_name + ".json")

			ScriptPath = os.path.join(current_path, "cfg_{}.json".format(file_name))
			cmdRun = '"{tool}" "{scene}" "{template}"\n'.format(tool="C:\\rprSdkWin64\\RprsRender64.exe", scene=scene, template=ScriptPath)
			cmdScriptPath = os.path.join(current_path, '{}.bat'.format(file_name))
			
			save_configured_files(ScriptPath, config_json, cmdScriptPath, cmdRun)

			p = psutil.Popen(cmdScriptPath, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			stdout, stderr = p.communicate()

			update_core_log(stdout, stderr)

			try:
				p.wait(timeout=timeout)
			except psutil.TimeoutExpired as err:
				invalid_rcs += 1
				for child in reversed(p.children(recursive=True)):
					child.terminate()
				p.terminate()

			# get render time
			try:
				with open(os.path.join(output_path, file_name + ".json")) as f:
					data = json.loads(f.read().replace("\\", "\\\\"))
				render_time += data['render.time.ms'] / 1000
			except:
				print("Error render")

			scenes_rendered += 1

	# preparing dict with output files for post
	files = {}
	output_files = os.listdir('Output')
	for output_file in output_files:
		if output_file.endswith('.json'):
			continue
		files.update({output_file: open(os.path.join('Output', output_file), 'rb')})
	logger.info("Output files: {}".format(files))

	# detect render status
	status = "Unknown"
	fail_reason = "Unknown"

	images = glob.glob(os.path.join('Output' ,'*.png'))
	if animation:
		total_frames_number = int(args.endFrame) - int(args.startFrame) + 1
	else:
		total_frames_number = len(scenes)
	frames_without_image = total_frames_number - len(images)
	if invalid_rcs == 0 and frames_without_image == 0:
		rc = 0
		logger.info("Render status: success")
		status = "Success"
	elif invalid_rcs < total_frames_number and frames_without_image < total_frames_number:
		rc = 0
		logger.info("Render status: success partially")
		status = "Success (partially)"
		logger.info("Fail reason: timeout expired for " + str(invalid_rcs) + " frames and no output image for " + str(frames_without_image) + " frames")
		fail_reason = "Timeout expired for " + str(invalid_rcs) + " frames and no output image for " + str(frames_without_image) + " frames"
	else:
		logger.info("Render status: failure")
		status = "Failure"
		if invalid_rcs == total_frames_number:
			rc = -1
			logger.info("Fail reason: timeout expired for all frames")
			fail_reason = "Timeout expired for all frames"
		elif frames_without_image == total_frames_number:
			rc = -1
			logger.info("Fail reason: rendering failed, no output image for all frames")
			fail_reason = "No output image for all frames"

	logger.info("Sending render time")
	render_time = round(render_time, 2)
	post_data = {'render_time': render_time, 'id': args.id, 'status':'render_info'}
	send_status(post_data, args.django_ip, args.login, args.password)

	logger.info("Sending results")
	post_data = {'status': status, 'fail_reason': fail_reason, 'id': args.id}
	send_results(post_data, files, args.django_ip, args.login, args.password)

if __name__ == "__main__":
	rc = main()
	exit(rc)
