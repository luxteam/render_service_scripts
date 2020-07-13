from py7zr import SevenZipFile
from zipfile import ZipFile
import shutil
import logging
import os

logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO,
                    format='%(asctime)s :: %(levelname)s :: %(message)s')


def update_scene_in_archive(archive_name, scene_name):
    if archive_name.endswith('.zip') or archive_name.endswith('.7z'):
        logging.info('Update {}'.format(archive_name))
        try:
            if archive_name.endswith('.zip'):
                with ZipFile(archive_name, 'w') as archive:
                    archive.write(scene_name)
            else:
                archive = SevenZipFile(archive_name, mode='w')
                archive.write(scene_name)
                archive.close()
        except Exception as e:
            logging.error(str(e))
            logging.error('No such archive')
