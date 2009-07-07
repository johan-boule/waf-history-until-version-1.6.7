#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy 2008

"""MacOSX related tools

To compile an executable into a Mac application bundle (a .app), set its 'mac_app' attribute
  obj.mac_app = True

To make a bundled shared library (a .bundle), set the 'mac_bundle' attribute:
  obj.mac_bundle = True
"""

import os, shutil, sys, platform
import TaskGen, Task, Build, Options, Utils
from TaskGen import taskgen, feature, after, before
from Logs import error, debug

# see WAF issue 285
# and also http://trac.macports.org/ticket/17059
@feature('cc', 'cxx')
@before('apply_lib_vars')
def set_macosx_deployment_target(self):
	if self.env['MACOSX_DEPLOYMENT_TARGET']:
		os.environ['MACOSX_DEPLOYMENT_TARGET'] = self.env['MACOSX_DEPLOYMENT_TARGET']
	elif 'MACOSX_DEPLOYMENT_TARGET' not in os.environ:
		if sys.platform == 'darwin':
			os.environ['MACOSX_DEPLOYMENT_TARGET'] = '.'.join(platform.mac_ver()[0].split('.')[:2])

@feature('cc', 'cxx')
@after('apply_lib_vars')
def apply_framework(self):
	for x in self.to_list(self.env['FRAMEWORKPATH']):
		frameworkpath_st = '-F%s'
		self.env.append_unique('CXXFLAGS', frameworkpath_st % x)
		self.env.append_unique('CCFLAGS', frameworkpath_st % x)
		self.env.append_unique('LINKFLAGS', frameworkpath_st % x)

	for x in self.to_list(self.env['FRAMEWORK']):
		self.env.append_value('LINKFLAGS', ['-framework', x])

@taskgen
@after('apply_link')
@feature('cprogram')
def create_task_macapp(self):
	"""Use env['MACAPP'] to force *all* executables to be transformed into Mac applications
	or use obj.mac_app = True to build specific targets as Mac apps"""
	if self.env['MACAPP'] or getattr(self, 'mac_app', False):
		apptask = self.create_task('macapp', self.env)
		apptask.set_inputs(self.link_task.outputs)

		out = self.link_task.outputs[0]

		bld = self.bld

		name = out.name
		k = name.rfind('.')
		if k >= 0:
			name = name[:k] + '.app'
		else:
			name = name + '.app'

		dir = out.parent.get_dir(name)
		if not dir:
			dir = out.__class__(name, out.parent, 1)
			bld.rescan(dir)
			contents = out.__class__('Contents', dir, 1)
			bld.rescan(contents)
			macos = out.__class__('MacOS', contents, 1)
			bld.rescan(macos)
			print dir, contents, macos

		print dir
		print "test 1", dir.find_dir(['Contents', 'MacOS'])

		n1 = dir.find_or_declare(['Contents', 'MacOS', out.name])
		print n1
		n2 = dir.find_or_declare('Contents/MacOS/Info.plist')
		print n2

		apptask.set_outputs([n1, n2])
		apptask.install_path = self.install_path + os.sep + name
		self.apptask = apptask

@after('apply_link')
@feature('cshlib')
def apply_link_osx(self):
	name = self.link_task.outputs[0].name
	if getattr(self, 'vnum', None):
		name = name.replace('.dylib', '.%s.dylib' % self.vnum)

	path = os.path.join(Utils.subst_vars(self.install_path, self.env), name)
	self.env.append_value('LINKFLAGS', '-install_name')
	self.env.append_value('LINKFLAGS', path)

@before('apply_link', 'apply_lib_vars')
@feature('cc', 'cxx')
def apply_bundle(self):
	"""use env['MACBUNDLE'] to force all shlibs into mac bundles
	or use obj.mac_bundle = True for specific targets only"""
	if not ('cshlib' in self.features or 'shlib' in self.features): return
	if self.env['MACBUNDLE'] or getattr(self, 'mac_bundle', False):
		self.env['shlib_PATTERN'] = self.env['macbundle_PATTERN']
		uselib = self.uselib = self.to_list(self.uselib)
		if not 'MACBUNDLE' in uselib: uselib.append('MACBUNDLE')

@after('apply_link')
@feature('cshlib')
def apply_bundle_remove_dynamiclib(self):
	if self.env['MACBUNDLE'] or getattr(self, 'mac_bundle', False):
		if not getattr(self, 'vnum', None):
			try:
				self.env['LINKFLAGS'].remove('-dynamiclib')
			except ValueError:
				pass

# TODO REMOVE IN 1.6 (global variable)
app_dirs = ['Contents', 'Contents/MacOS', 'Contents/Resources']

app_info = '''
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist SYSTEM "file://localhost/System/Library/DTDs/PropertyList.dtd">
<plist version="0.9">
<dict>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleGetInfoString</key>
	<string>Created by Waf</string>
	<key>CFBundleSignature</key>
	<string>????</string>
	<key>NOTE</key>
	<string>THIS IS A GENERATED FILE, DO NOT MODIFY</string>
	<key>CFBundleExecutable</key>
	<string>%s</string>
</dict>
</plist>
'''

def app_build(task):
	global app_dirs
	env = task.env

	shutil.copy(task.inputs[0].srcpath(env), task.outputs[0].abspath(env))

	f = open(task.outputs[1].abspath(env))
	f.write(app_info % os.path.basename(srcprg))
	f.close()

	return 0

def install_shlib(task):
	"""see http://code.google.com/p/waf/issues/detail?id=173"""
	nums = task.vnum.split('.')

	path = self.install_path

	libname = task.outputs[0].name

	name3 = libname.replace('.dylib', '.%s.dylib' % task.vnum)
	name2 = libname.replace('.dylib', '.%s.dylib' % nums[0])
	name1 = libname

	filename = task.outputs[0].abspath(task.env)
	bld = task.outputs[0].__class__.bld
	bld.install_as(path + name3, filename, env=task.env)
	bld.symlink_as(path + name2, name3)
	bld.symlink_as(path + name1, name3)

@feature('osx')
@after('install_target_cshlib')
def install_target_osx_cshlib(self):
	if not self.bld.is_install: return
	if getattr(self, 'vnum', '') and sys.platform != 'win32':
		self.link_task.install = install_shlib

Task.task_type_from_func('macapp', vars=[], func=app_build, after="cxx_link cc_link ar_link_static")

