import requests
import json
import argparse
from requests.auth import HTTPBasicAuth


def main():

	parser = argparse.ArgumentParser()
	parser.add_argument('--tool')
	parser.add_argument('--status')
	parser.add_argument('--id')
	parser.add_argument('--django_ip')
	parser.add_argument('--login')
	parser.add_argument('--password')
	args = parser.parse_args()

	django_url = args.django_ip

	post_data = {'status': args.status, 'id': args.id}
	response = requests.post(django_url, data=post_data, auth=HTTPBasicAuth(args.login, args.password))
	print(response)

if __name__ == "__main__":
	main()
	exit(0)