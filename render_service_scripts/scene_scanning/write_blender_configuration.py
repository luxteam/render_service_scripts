import bpy
import addon_utils
import json
import os
import pyrpr
from rprblender.utils.user_settings import get_user_settings



def initializeRPR():
	scene = bpy.context.scene
	enable_rpr_render(scene)
	set_value(scene.rpr.limits, 'seconds', 1)
	bpy.ops.render.render()


def set_value(path, name, value):
	if hasattr(path, name):
		setattr(path, name, value)
	else:
		print("No attribute found {{}}".format(name))


def get_value(path, name):
	if hasattr(path, name):
		return getattr(path, name)
	else:
		print("No attribute found ")


def enable_rpr_render(scene):
	if not addon_utils.check('rprblender')[0]:
		addon_utils.enable('rprblender', default_set=True, persistent=False, handle_error=None)
	set_value(scene.render, 'engine', 'RPR')


def set_render_device():
	render_device_settings = get_user_settings().final_devices
	set_value(render_device_settings, 'cpu_state', False)
	render_device_settings.gpu_states[0] = True
	device_name = pyrpr.Context.gpu_devices[0]['name']

	return device_name


def init(scene_path):
	# open scene
	bpy.ops.wm.open_mainfile(filepath=os.path.join(r"{res_path}", scene_path))
	# get scene
	scene = bpy.context.scene
	# enable rpr
	enable_rpr_render(scene)
	# Render device in RPR
	set_render_device()

	return scene


def render(scene_path):
	scene = init(scene_path)


	set_value(scene.rpr.limits, 'seconds', 1800)

	if {border_max_x}:
		set_value(scene.render, 'border_max_x', {border_max_x})
	if {border_max_y}:
		set_value(scene.render, 'border_max_y', {border_max_y})
	if {border_min_x}:
		set_value(scene.render, 'border_min_x', {border_min_x})
	if {border_min_y}:
		set_value(scene.render, 'border_min_y', {border_min_y})
	if {fps}:
		set_value(scene.render, 'fps', {fps})
	if {fps_base}:
		set_value(scene.render, 'fps_base', {fps_base})
	if {tile_x}:
		set_value(scene.render, 'tile_x', {tile_x})
	if {tile_y}:
		set_value(scene.render, 'tile_y', {tile_y})
	if "{camera}":
		for obj in bpy.data.objects:
			if (obj.type == 'CAMERA' and obj.name == "{camera}"):
				set_value(scene, 'camera', obj)

	# write and reopen scene
	bpy.ops.wm.save_as_mainfile(filepath=os.path.join(r"{res_path}", scene_path))
	
	scene = init(scene_path)

	# scene configuration json
	report = {{}}
	report['border_max_x'] = get_value(scene.render, 'border_max_x')
	report['border_max_y'] = get_value(scene.render, 'border_max_y')
	report['border_min_x'] = get_value(scene.render, 'border_min_x')
	report['border_min_y'] = get_value(scene.render, 'border_min_y')
	report['fps'] = get_value(scene.render, 'fps')
	report['fps_base'] = get_value(scene.render, 'fps_base')
	report['tile_x'] = get_value(scene.render, 'tile_x')
	report['tile_y'] = get_value(scene.render, 'tile_y')

	# convert set of missing files to list
	report['missing_files'] = list(bpy.ops.file.find_missing_files())

	report['active_camera'] = scene.camera.name
	report['cameras'] = []
	for obj in bpy.data.objects:
		if (obj.type == 'CAMERA'):
			report['cameras'].append(obj.name)

	with open(os.path.join(r"{res_path}", "scene_info.json"), 'w') as f:
		json.dump(report, f, indent=' ')


if __name__ == "__main__":
	initializeRPR()
	render(r'{scene_path}')
