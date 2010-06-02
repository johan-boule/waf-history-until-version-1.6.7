#! /usr/bin/env python

from wafadmin import Utils
from wafadmin import ConfigSet
ConfigSet.ConfigSet.copy = ConfigSet.ConfigSet.derive
ConfigSet.ConfigSet.set_variant = Utils.nada

from wafadmin import Build
Build.BuildContext.add_subdirs = Build.BuildContext.recurse
Build.BuildContext.name_to_obj = Build.BuildContext.get_tgen_by_name

from wafadmin import Configure
Configure.ConfigurationContext.sub_config = Configure.ConfigurationContext.recurse
Configure.conftest = Configure.conf

from wafadmin import Options
Options.OptionsContext.sub_options = Options.OptionsContext.recurse

from wafadmin.TaskGen import before, feature

@feature('d')
@before('apply_incpaths')
def old_importpaths(self):
	if getattr(self, 'importpaths', []):
		self.includes = self.importpaths

from wafadmin import Context
eld = Context.load_tool
def load_tool(*k, **kw):
	ret = eld(*k, **kw)
	return ret
	if 'set_options' in ret.__dict__:
		ret.options = ret.set_options
	if 'detect' in ret.__dict__ and not 'configure' in ret.__dict__:
		ret.configure = ret.detect
Context.load_tool = load_tool

rev = Context.load_module
def load_module(file_path):
	ret = rev(file_path)
	if 'set_options' in ret.__dict__:
		ret.options = ret.set_options
	return ret
Context.load_module = load_module

from wafadmin import Scripting
old = Scripting.set_main_module
def set_main_module(f):
	old(f)
	if 'set_options' in Context.g_module.__dict__:
		Context.g_module.options = Context.g_module.set_options
Scripting.set_main_module = set_main_module

from wafadmin import TaskGen
old_apply = TaskGen.task_gen.apply
def apply(self):
	self.features = self.to_list(self.features)
	if 'cstaticlib' in self.features:
		self.features.append('cstlib')
		self.features.remove('cstaticlib')
	old_apply(self)
TaskGen.task_gen.apply = apply

