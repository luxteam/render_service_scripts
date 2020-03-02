from py7zr import unpack_7zarchive
import shutil
import logging
import os

logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO,
                    format='%(asctime)s :: %(levelname)s :: %(message)s')

# configure 7z lib dependency
shutil.register_unpack_format('7zip', ['.7z'], unpack_7zarchive)


def unpack_scene():
    for entry in os.scandir('.'):
        if entry.name.endswith('.zip') or entry.name.endswith('.7z'):
            logging.info('Unpack {}'.format(entry.name))
            shutil.unpack_archive(entry.name, '.')
    logging.info('No one archive')


if __name__ == '__main__':
    unpack_scene()
