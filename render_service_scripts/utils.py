import requests
import os


class Util:
	def __init__(self, ip, logger):
		self.ip = ip
		self.logger = logger

	def send_status(self, post_data, files=None):
		try_count = 0
		while try_count < 3:
			try:
				response = requests.post(self.ip, data=post_data, files=files) if files \
					else requests.post(self.ip, data=post_data)
				if response.status_code == 200:
					self.logger.info("POST request successfuly sent.")
					break
				else:
					self.logger.info("POST reques failed, status code: " + str(response.status_code))
					break
			except Exception as e:
				if try_count == 2:
					self.logger.info("POST request try 3 failed. Finishing work.")
					break
				try_count += 1
				self.logger.info("POST request failed. Retry ...")

	@staticmethod
	def create_dir(path):
		if not os.path.exists(path):
			os.makedirs(path)

	@staticmethod
	def read_file(file_path):
		with open(file_path) as f:
			return f.read()

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
