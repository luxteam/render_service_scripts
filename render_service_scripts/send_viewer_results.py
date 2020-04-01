import requests
import json
import argparse
import os
import logging
from requests.auth import HTTPBasicAuth

# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO)
logger = logging.getLogger(__name__)


def main():

	parser = argparse.ArgumentParser()
	parser.add_argument('--status')
	parser.add_argument('--id')
	parser.add_argument('--django_ip')
	parser.add_argument('--build_number')
	parser.add_argument('--login')
	parser.add_argument('--password')
	args = parser.parse_args()

	# preparing dict with output files for post
	files = {}
	# search zip archive and logs
	output_files = os.listdir('.')
	for output_file in output_files:
		if output_file.endswith('.zip') or output_file.endswith('.txt'):
			files.update({output_file: open(output_file, 'rb')})
	# search output image and logs
	output_files = os.listdir('viewer_dir')
	for output_file in output_files:
		if output_file.endswith('.txt') or output_file == 'img0001.png':
			files.update({output_file: open(os.path.join('viewer_dir', output_file), 'rb')})
	logger.info("Output files: {}".format(files))

	post_data = {'status': args.status, 'id': args.id, 'build_number': args.build_number}

	try_count = 0
	while try_count < 3:
		try:
			response = requests.post(args.django_ip, data=post_data, files=files, auth=HTTPBasicAuth(args.login, args.password))
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
		
if __name__ == "__main__":
	main()


