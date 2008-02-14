#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

"Base for c++ programs and libraries"

import ccroot
from Params import debug
import Object, Params, Action, Utils

g_cpp_flag_vars = [
'FRAMEWORK', 'FRAMEWORKPATH',
'STATICLIB', 'LIB', 'LIBPATH', 'LINKFLAGS', 'RPATH',
'INCLUDE',
'CXXFLAGS', 'CCFLAGS', 'CPPPATH', 'CPPFLAGS', 'CXXDEFINES']
"main cpp variables"

EXT_CXX = ['.cpp', '.cc', '.cxx', '.C']

g_cpp_type_vars=['CXXFLAGS', 'LINKFLAGS', 'obj_ext']
class cppobj(ccroot.ccroot):
	def __init__(self, type='program', subtype=None):
		ccroot.ccroot.__init__(self, type, subtype)
		self.m_type_initials = 'cpp'

		self.cxxflags=''
		self.cppflags=''

		self.meth_order('apply_defines_cxx', 'apply_core', 'apply_lib_vars', 'apply_obj_vars_cxx', 'apply_obj_vars')

		global g_cpp_flag_vars
		self.p_flag_vars = g_cpp_flag_vars

		global g_cpp_type_vars
		self.p_type_vars = g_cpp_type_vars

def apply_obj_vars_cxx(self):
	debug('apply_obj_vars_cxx', 'ccroot')
	env = self.env
	app = self.env.append_unique
	cpppath_st = self.env['CPPPATH_ST']

	self.addflags('CXXFLAGS', self.cxxflags)

	# local flags come first
	# set the user-defined includes paths
	for i in self.bld_incpaths_lst:
		app('_CXXINCFLAGS', cpppath_st % i.bldpath(env))
		app('_CXXINCFLAGS', cpppath_st % i.srcpath(env))

	# set the library include paths
	for i in self.env['CPPPATH']:
		app('_CXXINCFLAGS', cpppath_st % i)
		#print self.env['_CXXINCFLAGS']
		#print " appending include ",i

	# this is usually a good idea
	app('_CXXINCFLAGS', cpppath_st % '.')
	app('_CXXINCFLAGS', cpppath_st % self.env.variant())
	tmpnode = Params.g_build.m_curdirnode
	app('_CXXINCFLAGS', cpppath_st % tmpnode.bldpath(env))
	app('_CXXINCFLAGS', cpppath_st % tmpnode.srcpath(env))
Object.gen_hook(apply_obj_vars_cxx)

def apply_defines_cxx(self):
	tree = Params.g_build
	lst = self.to_list(self.defines)+self.to_list(self.env['CXXDEFINES'])
	milst = []

	# now process the local defines
	for defi in lst:
		if not defi in milst:
			milst.append(defi)

	# CXXDEFINES_USELIB
	libs = self.to_list(self.uselib)
	for l in libs:
		val = self.env['CXXDEFINES_'+l]
		if val: milst += self.to_list(val)

	self.env['DEFLINES'] = ["%s %s" % (x[0], Utils.trimquotes('='.join(x[1:]))) for x in [y.split('=') for y in milst]]
	y = self.env['CXXDEFINES_ST']
	self.env['_CXXDEFFLAGS'] = [y%x for x in milst]
Object.gen_hook(apply_defines_cxx)

def cxx_hook(self, node):
	# create the compilation task: cpp or cc
	task = self.create_task('cpp', self.env)
	obj_ext = self.env[self.m_type+'_obj_ext']
	if not obj_ext: obj_ext = '.os'
	else: obj_ext = obj_ext[0]

	task.m_scanner = ccroot.g_c_scanner
	task.path_lst = self.inc_paths
	task.defines  = self.scanner_defines

	task.m_inputs = [node]
	task.m_outputs = [node.change_ext(obj_ext)]
	self.compiled_tasks.append(task)

def setup(bld):
	cpp_str = '${CXX} ${CXXFLAGS} ${CPPFLAGS} ${_CXXINCFLAGS} ${_CXXDEFFLAGS} ${CXX_SRC_F}${SRC} ${CXX_TGT_F}${TGT}'
	link_str = '${LINK_CXX} ${CPPLNK_SRC_F}${SRC} ${CPPLNK_TGT_F}${TGT} ${LINKFLAGS} ${_LIBDIRFLAGS} ${_LIBFLAGS}'

	Action.simple_action('cpp', cpp_str, color='GREEN', prio=100)
	Action.simple_action('cpp_link', link_str, color='YELLOW', prio=111)

	Object.register('cpp', cppobj)
	Object.declare_extension(EXT_CXX, cxx_hook)

