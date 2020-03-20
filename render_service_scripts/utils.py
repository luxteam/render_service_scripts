import argparse
import glob
import json
import subprocess
import psutil
import requests
import os


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

	@staticmethod
	def find_scene(*extensions, slash_replacer=None, is_maya=False):
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
		return scene[0]

	def format_template_with_args(self, template, res_path, scene_path, **kwargs):
		args = self.args
		if 'project' in kwargs:
			template = template.format(project=kwargs['project'])
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
