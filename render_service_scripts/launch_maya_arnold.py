import logging
from render_service_scripts.utils import MayaToolLauncher


# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'Output'


def main():
	launcher = MayaToolLauncher(logger, OUTPUT_DIR, 'Arnold')
	launcher.prepare_launch()
	return launcher.launch()

if __name__ == "__main__":
	rc = main()
	exit(rc)