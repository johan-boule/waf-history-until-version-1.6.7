#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2006 (ita)
# Ralf Habacker, 2006 (rh)

import os, sys
import Utils,Action,Params,Configure

# tool specific setup
# is called when a build process is started 
def setup(env):
	# by default - when loading a compiler tool, it sets CC_SOURCE_TARGET to a string
	# like '%s -o %s' which becomes 'file.cpp -o file.o' when called
	cpp_vardeps    = ['CXX', 'CXXFLAGS', '_CPPDEFFLAGS', '_CXXINCFLAGS', 'CXX_ST']
	Action.GenAction('cpp', cpp_vardeps)

	# TODO: this is the same definitions as for gcc, should be separated to have independent setup
	link_vardeps   = ['LINK', 'LINKFLAGS', 'LINK_ST', '_LIBDIRFLAGS', '_LIBFLAGS']
	Action.GenAction('link', link_vardeps)

# tool detection and initial setup 
# is called when a configure process is started, 
# the values are cached for further build processes
def detect(env):

	conf = Configure.Configure(env)
	comp = conf.checkProgram('g++')
	if not comp:
		return 1;

	# g++ requires ar for static libs
	if conf.checkTool('ar'):
		Utils.error('g++ needs ar - not found')
		return 1

	if not env['DESTDIR']: env['DESTDIR']=''
	if sys.platform == "win32": 
		if not env['PREFIX']: env['PREFIX']='c:\\'

		# c++ compiler
		env['CXX']             = comp
		env['_CPPDEFFLAGS']    = ''
		env['_CXXINCFLAGS']    = ''
		env['CXX_ST']          = '%s -c -o %s'
		env['CPPPATH_ST']      = '-I%s' # template for adding include pathes

		# linker	
		env['LINK']            = comp
		env['LINKFLAGS']       = []
		env['LIB']             = []
		env['LINK_ST']         = '%s -o %s'
		env['LIB_ST']          = '-l%s'	# template for adding libs
		env['LIBPATH_ST']      = '-L%s' # template for adding libpathes
		env['_LIBDIRFLAGS']    = ''
		env['_LIBFLAGS']       = ''
	
		# shared library 
		env['shlib_CXXFLAGS']  = ['']
		env['shlib_LINKFLAGS'] = ['-shared']
		env['shlib_obj_ext']   = ['.o']
		env['shlib_PREFIX']    = 'lib'
		env['shlib_SUFFIX']    = '.dll'
	
		# static library
		env['staticlib_LINKFLAGS'] = ['']
		env['staticlib_obj_ext'] = ['.o']
		env['staticlib_PREFIX']= 'lib'
		env['staticlib_SUFFIX']= '.a'
	
		# program 
		env['program_obj_ext'] = ['.o']
		env['program_SUFFIX']  = '.exe'

	else:
		if not env['PREFIX']: env['PREFIX'] = '/usr'

		# debug level
		if Params.g_options.debug_level == 'release':
			env['CXXFLAGS'] = '-O2'
		elif Params.g_options.debug_level == 'debug':
			env['CXXFLAGS'] = ['-g', '-DDEBUG']
		elif Params.g_options.debug_level == 'ultradebug':
			env['CXXFLAGS'] = ['-g3', '-O0', '-DDEBUG']
		else:
			env['CXXFLAGS'] = '-O2'

		# c++ compiler
		env['CXX']             = 'g++'
		env['_CPPDEFFLAGS']    = ''
		env['_CXXINCFLAGS']    = ''
		env['CXX_ST']          = '%s -c -o %s'
		env['CPPPATH_ST']      = '-I%s' # template for adding include pathes
	
		# linker
		env['LINK']            = 'g++'
		env['LINKFLAGS']       = []
		env['LIB']             = []
		env['LINK_ST']         = '%s -o %s'
		env['LIB_ST']          = '-l%s'	# template for adding libs
		env['LIBPATH_ST']      = '-L%s' # template for adding libpathes
		env['_LIBDIRFLAGS']    = ''
		env['_LIBFLAGS']       = ''
	
		# shared library 
		env['shlib_CXXFLAGS']  = ['-fPIC', '-DPIC']
		env['shlib_LINKFLAGS'] = ['-shared']
		env['shlib_obj_ext']   = ['.os']
		env['shlib_PREFIX']    = 'lib'
		env['shlib_SUFFIX']    = '.so'
	
		# static lib
		env['staticlib_LINKFLAGS'] = ['-Wl,-Bstatic']
		env['staticlib_obj_ext'] = ['.o']
		env['staticlib_PREFIX']= 'lib'
		env['staticlib_SUFFIX']= '.a'
	
		# program 
		env['program_obj_ext'] = ['.o']
		env['program_SUFFIX']  = ''
		
	return 0

