import argparse
import ctypes
import datetime
import glob
import json
import subprocess
import psutil
import requests
import os
from render_service_scripts.unpack import unpack_scene


class Util:
	def __init__(self, ip, logger, args):
		self.ip = ip
		self.logger = logger
		self.args = args

	def send_status(self, post_data, files=None):
		try_count = 0
		while try_count < 3:
			try:
				response = requests.post(self.ip, data=post_data, files=files) if files \
					else requests.post(self.ip, data=post_data)
				if response.status_code == 200:
					self.logger.info("POST request successfully sent.")
					break
				else:
					self.logger.info("POST request failed, status code: " + str(response.status_code))
					break
			except Exception as e:
				if try_count == 2:
					self.logger.info("POST request try 3 failed. Finishing work.")
					break
				try_count += 1
				self.logger.info("POST request failed. Retry ...")

	def create_info_post_data(self, data):
		return {'render_time': data['render_time'],
				'width': data['width'],
				'height': data['height'],
				'min_samples': data['min_samples'],
				'max_samples': data['max_samples'],
				'noise_threshold': data['noise_threshold'],
				'id': self.args.id,
				'status': 'render_info'}

	def send_render_info(self, info_json_file, **kwargs):
		self.logger.info("Sending render info")
		if os.path.exists(info_json_file):
			data = json.loads(self.read_file(info_json_file))
			data.update(kwargs)
			post_data = self.create_info_post_data(data)
			self.send_status(post_data)
		else:
			self.logger.info("Error. No render info!")

	@staticmethod
	def get_required_args(*arg_names):
		parser = argparse.ArgumentParser()
		for arg in arg_names:
			parser.add_argument(arg, required=True)
		return parser.parse_args()

	@staticmethod
	def get_render_args(*args):
		return Util.get_required_args('--django_ip', '--id', '--build_number', '--tool', '--min_samples',
									  '--max_samples', '--noise_threshold', '--startFrame', '--endFrame', '--width',
									  '--height', '--scene_name', *args)

	@staticmethod
	def get_file_name(path):
		return os.path.basename(path).split(".", 2)[0]

	@staticmethod
	def get_file_type(path):
		split_file_name = os.path.basename(path).split(".", 2)
		return split_file_name[1] if len(split_file_name) > 1 else None

	@staticmethod
	def create_dir(path):
		if not os.path.exists(path):
			os.makedirs(path)

	@staticmethod
	def read_file(file_path):
		with open(file_path) as f:
			return f.read()

	@staticmethod
	def save_render_file(script, file_name, ext):
		render_file = "render_{}.{}".format(file_name, ext)
		with open(render_file, 'w') as f:
			f.write(script)
		return render_file

	@staticmethod
	def update_license(file):
		with open(file) as f:
			scene_file = f.read()

		license = "fileInfo \"license\" \"student\";"
		scene_file = scene_file.replace(license, '')

		with open(file, "w") as f:
			f.write(scene_file)

	def find_scene(self, *extensions, slash_replacer=None, is_maya=False):
		scene = []
		for root_dir, dirs, files in os.walk(os.getcwd()):
			for file in files:
				for ext in extensions:
					if file.endswith(ext):
						if is_maya:
							try:
								Util.update_license(os.path.join(root_dir, file))
							except Exception:
								pass
						scene.append(os.path.join(root_dir, file))

		if slash_replacer:
			scene[0] = scene[0].replace("\\", slash_replacer)
		self.logger.info("Found scene: {}".format(scene[0]))
		return scene[0]

	def format_template_with_args(self, template, res_path, scene_path, project=None):
		args = self.args
		if project:
			return template.format(min_samples=args.min_samples,
								   max_samples=args.max_samples,
								   noise_threshold=args.noise_threshold,
								   width=args.width,
								   height=args.height,
								   startFrame=args.startFrame,
								   endFrame=args.endFrame,
								   res_path=res_path,
								   scene_path=scene_path,
								   project=project)
		else:
			return template.format(min_samples=args.min_samples,
								   max_samples=args.max_samples,
								   noise_threshold=args.noise_threshold,
								   width=args.width,
								   height=args.height,
								   startFrame=args.startFrame,
								   endFrame=args.endFrame,
								   res_path=res_path,
								   scene_path=scene_path)

	def create_files_dict(self, output_dir):
		files = {}
		output_files = os.listdir(output_dir)
		for output_file in output_files:
			files.update({output_file: open(os.path.join(output_dir, output_file), 'rb')})
		self.logger.info("Output files: {}".format(files))
		return files

	@staticmethod
	def get_images(output_dir, image_ext):
		return glob.glob(os.path.join(output_dir, '*{}'.format(image_ext)))

	def create_result_status_post_data(self, rc, output_dir):
		images = Util.get_images(output_dir, '.jpg')
		args = self.args
		status = "Unknown"
		fail_reason = "Unknown"

		if rc == 0 and images:
			self.logger.info("Render status: success")
			status = "Success"
		else:
			self.logger.info("Render status: failure")
			status = "Failure"
			if rc == -1:
				self.logger.info("Fail reason: timeout expired")
				fail_reason = "Timeout expired"
			elif not images:
				rc = -1
				self.logger.info("Fail reason: rendering failed, no output image")
				fail_reason = "No output image"
			else:
				rc = -1
				self.logger.info("Fail reason: unknown")
				fail_reason = "Unknown"

		self.logger.info("Sending results")
		post_data = {'status': status, 'fail_reason': fail_reason, 'id': args.id, 'build_number': args.build_number}
		return rc, post_data

	@staticmethod
	def start_render(render_bat_file):
		return psutil.Popen(render_bat_file, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

	@staticmethod
	def get_windows_titles():
		EnumWindows = ctypes.windll.user32.EnumWindows
		EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
		GetWindowText = ctypes.windll.user32.GetWindowTextW
		GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
		IsWindowVisible = ctypes.windll.user32.IsWindowVisible

		titles = []

		def foreach_window(hwnd, lParam):
			if IsWindowVisible(hwnd):
				length = GetWindowTextLength(hwnd)
				buff = ctypes.create_unicode_buffer(length + 1)
				GetWindowText(hwnd, buff, length + 1)
				titles.append(buff.value)
			return True

		EnumWindows(EnumWindowsProc(foreach_window), 0)

		return titles

	@staticmethod
	def get_tool_render_time(log_name, tool_name):
		with open(log_name, 'r') as file:
			for line in file.readlines():
				if "[{}] Rendering done - total time for 1 frames:".format(tool_name) in line:
					time_s = line.split(": ")[-1]

					try:
						x = datetime.datetime.strptime(time_s.replace('\n', '').replace('\r', ''), '%S.%fs')
					except ValueError:
						x = datetime.datetime.strptime(time_s.replace('\n', '').replace('\r', ''), '%Mm:%Ss')
					# 	TODO: proceed H:M:S

					return float(x.second + x.minute * 60 + float(x.microsecond / 1000000))


class RenderLauncher:
	def __init__(self, template_name,
				 output_dir,
				 logger,
				 # tool_path,
				 # cmd_command,
				 scene_ext,
				 res_path,
				 args,
				 is_maya=False,
				 slash_replacer_scene_find=None):
		self.template_name = template_name
		self.output_dir = output_dir
		self.logger = logger
		# self.tool_path = tool_path
		# self.cmd_command = cmd_command
		self.scene_ext = scene_ext
		self.res_path = res_path
		self.is_maya = is_maya
		self.slash_replacer_scene_find = slash_replacer_scene_find
		self.args = args
		self.scene = None
		self.scene_file_name = ""
		self.render_file = ""
		self.script = ""
		self.util = None

	def prepare_launch(self):
		# create util object
		self.util = Util(ip=self.args.django_ip, logger=self.logger, args=self.args)

		# create output folder for images and logs
		self.util.create_dir(self.output_dir)

		# unpack all archives
		unpack_scene(self.args.scene_name)
		self.scene = self.util.find_scene(*self.scene_ext,
										  slash_replacer=self.slash_replacer_scene_find,
										  is_maya=self.is_maya)

		project = None
		if self.is_maya:
			# detect project path for maya
			files = os.listdir(os.getcwd())
			zip_file = False
			for file in files:
				if file.endswith(".zip") or file.endswith(".7z"):
					zip_file = True
					project = "/".join(self.scene.split("/")[:-2])

			if not zip_file:
				project = self.res_path

		script_template = self.util.read_file(self.template_name)
		self.script = self.util.format_template_with_args(script_template,
														  res_path=self.res_path,
														  scene_path=self.scene,
														  project=project)
		self.scene_file_name = self.util.get_file_name(self.scene)
		self.render_file = self.util.save_render_file(self.script, self.scene_file_name,
													  self.util.get_file_type(self.template_name))

	def update_render_status(self, status, log_message):
		self.logger.info(log_message)
		post_data = {'status': status, 'id': self.args.id}
		self.util.send_status(post_data)

	def send_start_rendering(self):
		self.update_render_status('Rendering', "Starting rendering scene: {}".format(self.scene))

	def send_finish_rendering(self, ):
		self.update_render_status('Completed', "Finished rendering scene: {}".format(self.scene))

	def send_result_data(self, rc):
		files = self.util.create_files_dict(self.output_dir)
		rc, post_data = self.util.create_result_status_post_data(rc, self.output_dir)
		self.util.send_status(post_data, files)
		return rc


class MayaLauncher(RenderLauncher):
	def __init__(self, logger, output_dir):
		# parse command line args
		args = Util.get_render_args('--batchRender')
		RenderLauncher.__init__(self,
								args=args,
								template_name="maya_batch_render.py" if args.batchRender == "true" else "maya_render.py",
								output_dir=output_dir,
								logger=logger,
								scene_ext=['.ma', '.mb'],
								res_path=os.getcwd().replace("\\", "/") + "/",
								is_maya=True,
								slash_replacer_scene_find='/')


class MayaToolLauncher(RenderLauncher):
	def __init__(self, logger, output_dir, maya_tool_name):
		# parse command line args
		self.maya_tool_name = maya_tool_name
		args = Util.get_render_args()
		RenderLauncher.__init__(self,
								args=args,
								template_name="{}_render.py".format(maya_tool_name.lower()),
								output_dir=output_dir,
								logger=logger,
								scene_ext=['.ma', '.mb'],
								res_path=os.getcwd().replace("\\", "/") + "/",
								is_maya=True,
								slash_replacer_scene_find='/')

	def launch(self):
		render_file = self.util.get_file_name(self.render_file)
		cmd_command = '''
				set MAYA_CMD_FILE_OUTPUT=%cd%/{output_dir}/maya_render_log.txt
				set MAYA_SCRIPT_PATH=%cd%;%MAYA_SCRIPT_PATH%
				set PYTHONPATH=%cd%;%PYTHONPATH%
				"C:\\Program Files\\Autodesk\\Maya{tool}\\bin\\Render.exe" -r {maya_tool} -preRender "python(\\"import {render_file} as render\\"); python(\\"render.main()\\");" -log "{output_dir}\\batch_render_log.txt" -of jpg {maya_scene}
				'''.format(tool=self.args.tool, maya_scene=self.scene, render_file=render_file, maya_tool=self.maya_tool_name.lower(), output_dir=self.output_dir)
		render_bat_file = "launch_render_{}.bat".format(self.scene_file_name)
		with open(render_bat_file, 'w') as f:
			f.write(cmd_command)
		self.send_start_rendering()

		p = self.util.start_render(render_bat_file)

		# catch timeout ~30 minutes
		rc = 0
		try:
			stdout, stderr = p.communicate(timeout=2000)
		except (subprocess.TimeoutExpired, psutil.TimeoutExpired) as err:
			rc = -1
			for child in reversed(p.children(recursive=True)):
				child.terminate()
			p.terminate()

		self.send_finish_rendering()
		# send render info
		render_time = 0
		try:
			render_time = round(self.util.get_tool_render_time(os.path.join(self.output_dir, "maya_render_log.txt"), self.maya_tool_name),2)
		except:
			self.logger.info("Error. No render time!")
		self.util.send_render_info('render_info.json', render_time=render_time)
		rc = self.send_result_data(rc)

		return rc


class BlenderLauncher(RenderLauncher):
	def __init__(self, logger, output_dir):
		args = Util.get_render_args()
		RenderLauncher.__init__(self,
								args=args,
								template_name="blender_render.py",
								output_dir=output_dir,
								logger=logger,
								scene_ext=['.blend'],
								res_path=os.getcwd())
