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
		print("No attribute found {}".format(name))


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


def render(scene_path):

	# open scene
	bpy.ops.wm.open_mainfile(filepath=os.path.join('{{ res_path }}', scene_path))

	# get scene
	scene = bpy.context.scene

	# enable rpr
	enable_rpr_render(scene)

	# Render device in RPR
	set_render_device()

	set_value(scene.rpr.limits, 'seconds', 1800)

	# scene configuration json

	report = {}
	{% for option_structure in options_structure %}
	report['{{ option_structure }}'] = {}

		{% if options_structure[option_structure].type == 'value' %}

	report['{{ option_structure }}']['value'] = get_value({{ options_structure[option_structure].location }}, '{{ options_structure[option_structure].name }}')

		{% elif options_structure[option_structure].type == 'function' %}

	report['{{ option_structure }}']['elements'] = {{ options_structure[option_structure].location }}.{{ options_structure[option_structure].name }}(**{{ options_structure[option_structure].args }})

	if ('{{ option_structure }}' == 'missing_files'):
		report['{{ option_structure }}']['elements'] = list(report['{{ option_structure }}']['elements'])

		{% elif options_structure[option_structure].type == 'object' %}

	report['{{ option_structure }}']['elements'] = []

	report['{{ option_structure }}']['value'] = get_value({{ options_structure[option_structure].selected_location }}, '{{ options_structure[option_structure].selected_name }}')


	for obj in {{ options_structure[option_structure].location }}.{{ options_structure[option_structure].name }}:
		if (obj.type == '{{ options_structure[option_structure].obj_type }}'):
			report['{{ option_structure }}']['elements'].append(obj.name)

		{% endif  %}
	{% endfor %}

	with open(os.path.join('{{ res_path }}', "scene_info.json"), 'w') as f:
		json.dump(report, f, indent=' ')


if __name__ == "__main__":
	initializeRPR()
	render('{{ scene_path }}')
