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

        def create_dir(path):
            if not os.path.exists(path):
                os.makedirs(path)
