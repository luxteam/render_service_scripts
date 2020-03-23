import os
import subprocess
import psutil
import logging
from render_service_scripts.utils import MaxLauncher


# logging
logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'Output'


def main():
	launcher = MaxLauncher(logger, OUTPUT_DIR)
	launcher.prepare_launch()
	args = launcher.args
	util = launcher.util
	filename = launcher.scene_file_name
	render_file = launcher.render_file

	# save bat file
	cmd_command = '''
		"C:\\Program Files\\Autodesk\\3ds Max {tool}\\3dsmax.exe" -U MAXScript "{render_file}" -silent
		'''.format(tool=args.tool, render_file=render_file)
	render_bat_file = "launch_render_{}.bat".format(filename)
	with open(render_bat_file, 'w') as f:
		f.write(cmd_command)

	launcher.send_start_rendering()

	# start render
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
			fatal_errors_titles = ['Radeon ProRender', 'AMD Radeon ProRender debug assert', os.getcwd() + ' - MAXScript',
			'3ds Max', 'Microsoft Visual C++ Runtime Library', '3ds Max Error Report',
			'3ds Max application', 'Radeon ProRender Error', 'Image I/O Error', 'Warning', 'Error']
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

	launcher.send_finish_rendering()
	rc = launcher.send_result_data(rc)

	return rc


if __name__ == "__main__":
	rc = main()
	exit(rc)
