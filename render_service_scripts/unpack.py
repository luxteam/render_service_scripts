from py7zr import unpack_7zarchive
import shutil
import logging
import os

logging.basicConfig(filename="launch_render_log.txt", level=logging.INFO,
                    format='%(asctime)s :: %(levelname)s :: %(message)s')

# configure 7z lib dependency
shutil.register_unpack_format('7zip', ['.7z'], unpack_7zarchive)


def unpack_scene(scene_name, delete=False, output_dir='.'):
    if scene_name.endswith('.zip') or scene_name.endswith('.7z'):
        try:
            logging.info('Unpack {}'.format(scene_name))
            shutil.unpack_archive(scene_name, output_dir)
            if delete:
                logging.info('Delete archive {}'.format(scene_name))
                os.remove(scene_name)
        except Exception as e:
            logging.error(str(e))
            logging.error('No such archive')


def unpack_all(dir, delete=False, output_dir='.'):
    for entry in os.scandir(dir):
        if entry.name.endswith('.zip') or entry.name.endswith('.7z'):
            unpack_scene(entry.path, delete, output_dir)


if __name__ == '__main__':
    unpack_scene('..')
